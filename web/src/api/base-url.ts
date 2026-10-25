/** A public backend origin, never a credential. Website defaults to Vite/same-origin /api. */
export function apiUrl(path: string, configuredOrigin: string | undefined, native: boolean): string {
  if (!path.startsWith('/') || path.startsWith('//')) throw new Error('Invalid API path.');
  const origin = configuredOrigin?.trim();
  if (!origin) {
    if (native) throw new Error('The iOS app needs a reachable HTTPS backend. Set VITE_API_BASE_URL and rebuild the app.');
    return `/api${path}`;
  }
  const url = new URL(origin);
  if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash || url.pathname !== '/') {
    throw new Error('VITE_API_BASE_URL must be an HTTPS origin without credentials, a path or query.');
  }
  if (native && ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)) {
    throw new Error('Use a reachable HTTPS backend, not the iPhone’s localhost.');
  }
  return `${url.origin}/api${path}`;
}
