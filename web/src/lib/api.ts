export class APIError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export async function api<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {credentials: 'same-origin', signal, ...(body === undefined ? {} : {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)})});
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw new APIError(0, 'Couldn’t reach Ishara. Check your connection and try again.');
  }
  if (!response.ok) {
    const messages: {[key: number]: string} = {
      401: 'Your session has expired. Unlock the call desk again.',
      403: 'That number isn’t enabled for this demo. Choose an approved contact.',
      404: 'This call is no longer available. Start a new call.',
      422: 'Check your details and try again.',
      429: 'Wait a minute before trying again.',
      502: 'The calling service couldn’t start the call. Check the recipient’s Bolna verification and try again.',
      503: 'The service isn’t ready. Give it a moment, then try again.',
    };
    throw new APIError(response.status, messages[response.status] ?? 'Something interrupted the request. Try again.');
  }
  return response.status === 204 ? undefined as T : await response.json() as T;
}
