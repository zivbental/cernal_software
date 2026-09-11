function T = candidatesToTable(candidates)
%CANDIDATESTOTABLE Flatten a decoded /api/design/{id}/results candidates array into a
%   MATLAB table: one row per candidate, one column per metric raw_value alongside the
%   candidate's own fields. So writetable/sortrows/groupsummary work immediately.

    if isempty(candidates)
        T = table();
        return
    end
    if isstruct(candidates)
        candidates = num2cell(candidates);
    end

    rows = cell(numel(candidates), 1);
    for i = 1:numel(candidates)
        c = candidates{i};
        row = struct( ...
            'id', string(c.id), ...
            'engine_ref', string(c.engine_ref), ...
            'rank', valueOrNaN(c, 'rank'), ...
            'overall_score', valueOrNaN(c, 'overall_score'), ...
            'gate_family', string(c.gate_family), ...
            'logic_type', string(c.logic_type), ...
            'is_rejected', c.is_rejected, ...
            'rejection_reason', string(c.rejection_reason), ...
            'output', stringOrMissing(c, 'output'));

        if isfield(c, 'metrics')
            metrics = c.metrics;
            if isstruct(metrics)
                metrics = num2cell(metrics);
            end
            for m = 1:numel(metrics)
                metric = metrics{m};
                row.(metric.name) = metric.raw_value;
            end
        end
        rows{i} = row;
    end

    T = struct2table([rows{:}]);
end

function v = valueOrNaN(s, field)
    if isfield(s, field) && ~isempty(s.(field))
        v = s.(field);
    else
        v = NaN;
    end
end

function v = stringOrMissing(s, field)
    if isfield(s, field) && ~isempty(s.(field))
        v = string(s.(field));
    else
        v = string(missing);
    end
end
