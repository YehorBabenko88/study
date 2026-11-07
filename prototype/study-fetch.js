/* Same-origin mutation bootstrap. Server-side validation remains authoritative. */
(() => {
  const originalFetch = window.fetch.bind(window);
  let bootstrap;
  async function csrfToken() {
    if (!bootstrap) {
      bootstrap = originalFetch('/v1/security/bootstrap', {
        credentials: 'same-origin', cache: 'no-store', redirect: 'error'
      }).then(async response => {
        if (!response.ok) throw new Error('Study security bootstrap failed');
        const data = await response.json();
        if (typeof data.csrf_token !== 'string' || !data.csrf_token) {
          throw new Error('Study security token unavailable');
        }
        return data.csrf_token;
      }).catch(error => { bootstrap = undefined; throw error; });
    }
    return bootstrap;
  }
  window.fetch = async (input, options) => {
    const request = new Request(input, options);
    const url = new URL(request.url);
    if (url.origin !== location.origin || ['GET', 'HEAD', 'OPTIONS'].includes(request.method)) {
      return originalFetch(request);
    }
    const headers = new Headers(request.headers);
    headers.set('X-Study-CSRF', await csrfToken());
    return originalFetch(new Request(request, {headers}));
  };
})();
