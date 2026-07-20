export class DjsonApiClientError extends Error {
  constructor(
    public status: number,
    public title = "",
    public detail = "",
  ) {
    super(`[${status}] ${title}: ${detail}`)
  }
}

export class BadRequest extends DjsonApiClientError {}
export class Unauthorized extends DjsonApiClientError {}
export class Forbidden extends DjsonApiClientError {}
export class NotFound extends DjsonApiClientError {}
export class MethodNotAllowed extends DjsonApiClientError {}
export class Conflict extends DjsonApiClientError {}
export class UnprocessableEntity extends DjsonApiClientError {}
export class TooManyRequests extends DjsonApiClientError {}
export class InternalServerError extends DjsonApiClientError {}

const standardExcNames: Record<number, typeof DjsonApiClientError> = {
  400: BadRequest,
  401: Unauthorized,
  403: Forbidden,
  404: NotFound,
  405: MethodNotAllowed,
  409: Conflict,
  422: UnprocessableEntity,
  429: TooManyRequests,
  500: InternalServerError,
}

export function excClassFor(status: number): typeof DjsonApiClientError {
  return standardExcNames[status] ?? DjsonApiClientError
}
