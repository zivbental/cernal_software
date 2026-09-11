function newErr = translateError(err)
%TRANSLATEERROR Map a webread/webwrite HTTP exception onto a typed cernal error.
%   Best-effort: MATLAB's web functions do not reliably expose the JSON error body on
%   a non-2xx response across versions, so this maps on the STATUS CODE parsed from
%   err.identifier/err.message — not detail.did_you_mean or Retry-After. jsondecode
%   mangles field names that are not valid MATLAB identifiers, but every field this
%   client ever reads (the nine metric names included) is already a valid one.

    statusCode = NaN;
    tokens = regexp(err.identifier, 'HTTP(\d{3})', 'tokens', 'once');
    if isempty(tokens)
        tokens = regexp(err.message, '(\d{3})', 'tokens', 'once');
    end
    if ~isempty(tokens)
        statusCode = str2double(tokens{1});
    end

    switch statusCode
        case 401
            id = 'cernal:AuthError';
        case 422
            id = 'cernal:ValidationError';
        case 429
            id = 'cernal:RateLimited';
        otherwise
            id = 'cernal:RequestError';
    end

    newErr = MException(id, '%s', err.message);
    newErr = addCause(newErr, err);
end
