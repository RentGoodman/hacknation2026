# RentGoodman

Rental housing rules by address, with source citations and AI chat.

## Run locally

```sh
cp .env.example .env.local
npm run build
npm run dev
```

Set `ANTHROPIC_API_KEY` in `.env.local` to enable chat. Open [localhost:4173](http://127.0.0.1:4173).

## Deploy

Import the repository root into Vercel. The included `vercel.json` handles the build configuration. Add `ANTHROPIC_API_KEY` to the deployment's environment variables.
