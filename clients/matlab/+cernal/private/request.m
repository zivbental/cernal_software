function result = request(client, method, path, body, query, needsAuth, raw)
%REQUEST One HTTP call to the CERNAL API (docs/public-api.md §11.3).
%   webwrite/webread/weboptions only — built into base MATLAB, no toolbox required.
%   That constraint is the point: a client needing the Bioinformatics Toolbox is a
%   client half the users cannot run.
%
%   Package-private: callable unqualified from any function inside +cernal, not from
%   outside it.

    if nargin < 7
        raw = false;
    end
    if nargin < 6
        needsAuth = true;
    end

    url = [client.BaseURL path];
    if ~isempty(fieldnames(query))
        parts = {};
        fields = fieldnames(query);
        for i = 1:numel(fields)
            parts{end + 1} = [fields{i} '=' char(string(query.(fields{i})))]; %#ok<AGROW>
        end
        url = [url '?' strjoin(parts, '&')];
    end

    headerFields = {'Accept', 'application/json'};
    if needsAuth
        headerFields = [headerFields, {'X-API-Key', client.ApiKey}];
    end

    options = weboptions( ...
        'Timeout', client.Timeout, ...
        'ContentType', 'json', ...
        'MediaType', 'application/json', ...
        'HeaderFields', headerFields, ...
        'RequestMethod', lower(method));

    try
        if strcmpi(method, 'GET')
            if raw
                result = webread(url, options);
            else
                result = webread(url, options);
            end
        else
            if isempty(fieldnames(body))
                result = webwrite(url, struct(), options);
            else
                result = webwrite(url, body, options);
            end
        end
    catch err
        throwAsCaller(translateError(err));
    end
end
