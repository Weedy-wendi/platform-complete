# Pingce Frontend

Vue 3 + TypeScript + Vite + Element Plus + Pinia + Vue Router.

```bash
npm install
npm run gen:api       # regenerates src/types/api.ts from specs/017-rest-api/contracts/openapi.yaml
npm run dev
npm run typecheck
npm test
npm run build
```

- API access is only through `/v1` via `src/api/client.ts`.
- API types are generated; never edit `src/types/api.ts` by hand.
- The API key is kept in `sessionStorage`, never in URLs or `localStorage`.
