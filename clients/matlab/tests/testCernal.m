classdef testCernal < matlab.unittest.TestCase
    % Submits the shared fixture (clients/fixtures/) against a live MockEngine server
    % and checks the exact candidate column set (docs/public-api.md §11.4). Skipped
    % unless CERNAL_TEST_BASE_URL/CERNAL_TEST_API_KEY are set — matching
    % docs/public-api.md §11.4: MATLAB conformance is a manual, pre-release run, not
    % a CI job (no licence to spend on it for an iGEM team).
    %
    % Run with: results = runtests('testCernal')

    properties
        BaseURL
        ApiKey
        Fixture
        ExpectedColumns
    end

    methods (TestClassSetup)
        function setUp(testCase)
            testCase.BaseURL = getenv('CERNAL_TEST_BASE_URL');
            testCase.ApiKey = getenv('CERNAL_TEST_API_KEY');
            testCase.assumeFalse(isempty(testCase.BaseURL) || isempty(testCase.ApiKey), ...
                'CERNAL_TEST_BASE_URL/CERNAL_TEST_API_KEY not set — skipping.');

            here = fileparts(mfilename('fullpath'));
            fixturesDir = fullfile(here, '..', '..', 'fixtures');
            testCase.Fixture = jsondecode(fileread(fullfile(fixturesDir, 'design_request.json')));
            testCase.ExpectedColumns = jsondecode( ...
                fileread(fullfile(fixturesDir, 'expected_columns.json')));
        end
    end

    methods (Test)
        function fixtureRequestReturnsExpectedColumns(testCase)
            c = cernal.Client(testCase.ApiKey, 'BaseURL', testCase.BaseURL);
            args = namedArgsFromStruct(testCase.Fixture);
            job = c.design(args{:}, 'wait', 5);

            testCase.verifyEqual(job.currentStatus(), 'COMPLETED');
            T = job.results();
            testCase.verifyGreaterThan(height(T), 0);
            testCase.verifyLessThanOrEqual(height(T), testCase.Fixture.top_n);

            expected = sort(string(testCase.ExpectedColumns.candidate_columns));
            actual = sort(string(T.Properties.VariableNames));
            testCase.verifyTrue(all(ismember(expected, actual)));
        end

        function capabilitiesNeedsNoKey(testCase)
            c = cernal.Client('unused', 'BaseURL', testCase.BaseURL);
            body = c.capabilities();
            names = {body.gate_families.name};
            testCase.verifyTrue(any(strcmp(names, 'toehold')));
        end

        function badKeyRaisesAuthError(testCase)
            c = cernal.Client('cern_live_definitely-not-real', 'BaseURL', testCase.BaseURL);
            testCase.verifyError( ...
                @() c.design('trigger_sequence', 'AUGGCUAAGCUUAACGGAUCC', 'organism', 'ecoli'), ...
                'cernal:AuthError');
        end

        function unknownConstraintNamesTheTypo(testCase)
            c = cernal.Client(testCase.ApiKey, 'BaseURL', testCase.BaseURL);
            testCase.verifyError(@() c.design( ...
                'trigger_sequence', 'AUGGCUAAGCUUAACGGAUCC', ...
                'organism', 'ecoli', ...
                'constraints', struct('max_trigger', 2)), ...
                'cernal:ValidationError');
        end
    end
end

function args = namedArgsFromStruct(s)
    fields = fieldnames(s);
    args = cell(1, 2 * numel(fields));
    args(1:2:end) = fields;
    for i = 1:numel(fields)
        args{2 * i} = s.(fields{i});
    end
end
