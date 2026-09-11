classdef Job
    %JOB A submitted design (docs/public-api.md §8). Returned by Client.design.
    %   job = c.design(...); T = job.wait().results();
    %
    %   Already resolved if the server answered inline — a 'wait' that finished
    %   before its deadline, or an idempotent resubmission of an already-completed
    %   run — in which case wait() is a no-op.

    properties (SetAccess = private)
        Client
        Response
    end

    methods
        function obj = Job(client, response)
            obj.Client = client;
            obj.Response = response;
        end

        function s = currentStatus(obj)
            s = obj.Response.status;
        end

        function obj = wait(obj, varargin)
            %WAIT Poll with backoff (2s, growing to MaxPoll, up to Timeout overall)
            %   until the run reaches a terminal state.
            p = inputParser;
            addParameter(p, 'Timeout', 300);
            addParameter(p, 'Poll', 2);
            addParameter(p, 'MaxPoll', 15);
            parse(p, varargin{:});

            if isfield(obj.Response, 'candidates')
                return
            end
            if ~isfield(obj.Response, 'job_id') || isempty(obj.Response.job_id)
                error('cernal:Job:wait:noJobId', ...
                    'This job was never submitted (dry_run has no id to wait on).');
            end

            terminal = {'COMPLETED', 'FAILED', 'CANCELLED'};
            deadline = datetime('now') + seconds(p.Results.Timeout);
            delay = p.Results.Poll;
            state = obj.Response.status;

            while ~ismember(state, terminal)
                remaining = seconds(deadline - datetime('now'));
                if remaining <= 0
                    error('cernal:Job:wait:timeout', ...
                        'Job %s did not finish within %g s.', obj.Response.job_id, p.Results.Timeout);
                end
                pause(min(delay, remaining));
                obj.Response = obj.Client.status(obj.Response.job_id);
                state = obj.Response.status;
                delay = min(delay * 1.5, p.Results.MaxPoll);
            end

            if ~strcmp(state, 'COMPLETED')
                summary = '';
                if isfield(obj.Response, 'error_summary')
                    summary = obj.Response.error_summary;
                end
                error('cernal:Job:wait:runFailed', 'Run %s ended %s. %s', ...
                    obj.Response.job_id, state, summary);
            end

            obj.Response = obj.Client.results(obj.Response.job_id);
        end

        function T = results(obj)
            %RESULTS Ranked candidates as a MATLAB table.
            if ~isfield(obj.Response, 'candidates')
                error('cernal:Job:results:notReady', 'Call wait() before results().');
            end
            T = candidatesToTable(obj.Response.candidates);
        end

        function row = best(obj)
            %BEST The highest-ranked candidate, as a one-row table.
            T = obj.results();
            if height(T) == 0
                row = table();
            else
                row = T(1, :);
            end
        end

        function artifact(obj, kind, path)
            %ARTIFACT Save the first artifact of KIND to PATH. Fetched fresh — a
            %   prior include_artifacts at submission time is not required.
            body = obj.Client.results(obj.Response.job_id, 'include_artifacts', kind);
            if ~isfield(body, 'artifacts') || isempty(body.artifacts)
                error('cernal:Job:artifact:notFound', ...
                    "No artifact of kind '%s' on job %s.", kind, obj.Response.job_id);
            end
            artifacts = body.artifacts;
            if isstruct(artifacts)
                artifacts = num2cell(artifacts);
            end
            matches = artifacts(cellfun(@(a) strcmp(a.kind, kind), artifacts));
            if isempty(matches)
                error('cernal:Job:artifact:notFound', ...
                    "No artifact of kind '%s' on job %s.", kind, obj.Response.job_id);
            end
            obj.Client.downloadArtifact(matches{1}.id, path);
        end
    end
end
