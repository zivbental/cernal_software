classdef Client
    %CLIENT CERNAL API client (docs/public-api.md §11.3).
    %
    %   c = cernal.Client(apiKey, 'BaseURL', 'https://your-cernal-host');
    %   job = c.design('trigger_sequence', 'AUGGCUAAGCUUAACGGAUCC', 'organism', 'ecoli');
    %   T = job.wait().results();
    %
    %   webwrite/webread/weboptions only — built into base MATLAB, no toolbox
    %   required. That constraint is the point: a client needing the Bioinformatics
    %   Toolbox is a client half the users cannot run.

    properties (SetAccess = private)
        ApiKey
        BaseURL
        Timeout
    end

    methods
        function obj = Client(apiKey, varargin)
            if nargin < 1 || isempty(apiKey)
                apiKey = getenv('CERNAL_API_KEY');
            end
            if isempty(apiKey)
                error('cernal:Client:noApiKey', ...
                    'No API key. Pass apiKey, or set CERNAL_API_KEY.');
            end

            p = inputParser;
            addParameter(p, 'BaseURL', '', @(x) ischar(x) || isstring(x));
            addParameter(p, 'Timeout', 30, @isnumeric);
            parse(p, varargin{:});

            if isempty(p.Results.BaseURL)
                error('cernal:Client:noBaseURL', ['BaseURL is required, e.g. ' ...
                    'cernal.Client(key, ''BaseURL'', ''https://your-cernal-host'').']);
            end

            obj.ApiKey = char(apiKey);
            obj.BaseURL = regexprep(char(p.Results.BaseURL), '/$', '');
            obj.Timeout = p.Results.Timeout;
        end

        function job = design(obj, varargin)
            %DESIGN Submit a design request.
            %   Name-value pairs match docs/public-api.md §9 field names exactly
            %   (snake_case, not MATLAB's usual PascalCase) — 'trigger_sequence',
            %   'organism', 'constraints' (a struct), 'scoring' (a struct), etc.
            %   Two reserved keys are not sent as body fields: 'wait' (seconds to
            %   block server-side) and 'dry_run' (estimate without submitting).
            if mod(numel(varargin), 2) ~= 0
                error('cernal:Client:design:oddArgs', 'Expected name-value pairs.');
            end

            query = struct();
            body = struct();
            for i = 1:2:numel(varargin)
                key = varargin{i};
                value = varargin{i + 1};
                if strcmpi(key, 'wait')
                    query.wait = value;
                elseif strcmpi(key, 'dry_run')
                    if value
                        query.dry_run = 'true';
                    end
                else
                    body.(key) = value;
                end
            end

            response = request(obj, 'POST', '/api/design', body, query, true);
            job = cernal.Job(obj, response);
        end

        function s = status(obj, jobId)
            %STATUS The status of a job, without waiting.
            s = request(obj, 'GET', ['/api/design/' jobId], struct(), struct(), true);
        end

        function s = results(obj, jobId, varargin)
            %RESULTS Ranked candidates, raw (decoded JSON) — Job.results() returns a
            %   table; this is what it calls.
            query = struct(varargin{:});
            s = request(obj, 'GET', ['/api/design/' jobId '/results'], struct(), query, true);
        end

        function s = capabilities(obj)
            %CAPABILITIES Gate families, scoring metrics and their units. No key needed.
            s = request(obj, 'GET', '/api/version', struct(), struct(), false);
        end

        function downloadArtifact(obj, artifactId, path)
            %DOWNLOADARTIFACT Save one artifact to PATH.
            url = [obj.BaseURL '/api/artifacts/' artifactId '/download'];
            options = weboptions('HeaderFields', {'X-API-Key', obj.ApiKey}, ...
                'Timeout', obj.Timeout);
            websave(path, url, options);
        end
    end
end
