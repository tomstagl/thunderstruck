export type ResponseEvent = {
  url: string;
  statusCode: number;
  isFromCache: boolean;
};

export function describe(response: { fromCache?: boolean }) {
  return response.fromCache ? 'cached' : 'network';
}
