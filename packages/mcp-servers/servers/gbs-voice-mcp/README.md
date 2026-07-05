# gbs-voice MCP Server

MCP server that exposes the live **gbs-voice** service (transcription, TTS,
transcript cleanup, health) as MCP tools, so Claude Code / PAI Pulse / any MCP
client can call voice operations through the frozen **VoiceProvider seam
contract** (`gbs-voice/docs/SEAM_CONTRACT.md` v1) — never a vendor SDK.

- **Service:** `https://gbs-voice.wittycliff-d624a17c.westus2.azurecontainerapps.io`
- **Transport:** stdio (spawned by the MCP client)
- **Runtime deps:** `@modelcontextprotocol/sdk` only. No `openai`, no vendor
  voice SDK, no axios — native `fetch` (Node ≥ 20).

## PHI posture (fail-closed)

Per contract §3/§5 the `phi` flag defaults to `true` (an absent flag means
PHI). This server is stricter than the wire default:

| Tool | `phi` | Notes |
|------|-------|-------|
| `voice_transcribe` | **locked `true`** | Never exposed; audio only ever reaches BAA-covered providers. |
| `voice_cleanup` | **locked `true`** | BAA-covered cleanup models only. |
| `voice_speak` | defaults `true`, accepts explicit `false` | Pass `phi:false` **only** for non-PHI text (UI copy) to unlock premium non-BAA voices. |
| `voice_health` | n/a | Unauthenticated `GET /health`. |

## Tools

| Tool | Method + path | Input | Returns |
|------|---------------|-------|---------|
| `voice_transcribe` | `POST /v1/audio/transcriptions` (multipart) | `audioPath` (sandboxed, see below) **or** `audioBase64` (+ `filename`), `language?`, `cleanup?` (`none`\|`format`), `sessionId?` | `{ text, cleaned_text?, language, duration_s, provider, fallback }` |
| `voice_speak` | `POST /v1/audio/speech` (JSON, `stream:false`) | `text` (req), `voice?`, `style?`, `speed?`, `responseFormat?` (`mp3`\|`wav`\|`pcm`), `phi?`, `returnBase64?`, `sessionId?` | `{ audioPath, bytes, contentType, provider, fallback, phi }` (file written to output dir), or `{ audioBase64, ... }` when `returnBase64:true` |
| `voice_cleanup` | `POST /v1/text/cleanup` (JSON) | `text` (req), `mode?` (`dictation`\|`notes`\|`verbatim-punctuation`), `sessionId?` | `{ text, model, verbatim_guard }` (`pass`\|`fail`; on `fail` the raw text is returned unchanged) |
| `voice_health` | `GET /health` | — | `{ status, providers: { selfhosted, azure-speech, … } }` |

## Configuration

The API key is **server-side only** and comes from the environment
(`GBS_VOICE_API_KEY`). It is never hardcoded, never logged, and never included
in tool output (a scrub guard redacts the key value from every returned string;
see `src/tools.ts`).

| Env var | Required | Default |
|---------|----------|---------|
| `GBS_VOICE_API_KEY` | for authenticated tools | — (transcribe/speak/cleanup return `VOICE_UNAUTHENTICATED` / 401 without it) |
| `GBS_VOICE_BASE_URL` | no | the live service URL above |
| `GBS_VOICE_OUTPUT_DIR` | no | `<os.tmpdir()>/gbs-voice-mcp` (where `voice_speak` writes audio) |
| `GBS_VOICE_INPUT_DIR` | no | `process.cwd()` — sandbox root for `voice_transcribe`'s `audioPath` (see below) |
| `GBS_VOICE_MAX_AUDIO_BYTES` | no | `26214400` (25 MB) cap on any audio read or TTS response |

### `audioPath` is sandboxed (arbitrary-file exfiltration guard)

`voice_transcribe` uploads audio bytes to the remote service, so an unrestricted
`audioPath` would let a caller read **any** file the process can (`~/.ssh/id_rsa`,
`.env`, `/etc/passwd`) and exfiltrate it. This server therefore locks `audioPath`
down before it ever reads a byte:

1. **Sandbox root** — the path must resolve inside `GBS_VOICE_INPUT_DIR`
   (default: cwd). `../` traversal is rejected lexically.
2. **Symlink defense** — the file and the root are `realpath()`-resolved and the
   containment check is re-run, so a symlink inside the root that points outside
   is rejected.
3. **Extension allowlist** — only `.wav/.mp3/.m4a/.ogg/.flac/.webm`.
4. **Size cap** — files over `GBS_VOICE_MAX_AUDIO_BYTES` are rejected via
   `stat()` before read.
5. **Magic-byte sniff** — the content must actually match a known audio
   container signature; a secret renamed `secret.wav` is rejected.

Rejections throw a clear error and **never upload** — nothing leaves the box.
Set `GBS_VOICE_INPUT_DIR` to the directory your audio actually lives in (or pass
audio inline as `audioBase64`, which is size-capped and sniffed the same way).

Per-consumer keys live in Key Vault `kv-gbs-platform` as
`gbs-voice-key-<consumer>` (e.g. `gbs-voice-key-pai-pulse`). Retrieve at
runtime — never commit the value.

### Register with Claude Code

Build first (`npm install && npm run build`), then add to your `.mcp.json`
(or `~/.claude.json`). Supply the key via env — do not paste it into the file
if the file is tracked:

```jsonc
{
  "mcpServers": {
    "gbs-voice": {
      "command": "node",
      "args": ["${MCP_SERVERS_DIR}/servers/gbs-voice-mcp/build/index.js"],
      "env": {
        "GBS_VOICE_API_KEY": "${GBS_VOICE_API_KEY}",
        "GBS_VOICE_BASE_URL": "https://gbs-voice.wittycliff-d624a17c.westus2.azurecontainerapps.io"
      },
      "description": "[GBS] gbs-voice MCP - transcription, TTS, transcript cleanup, health via the VoiceProvider seam contract."
    }
  }
}
```

Then `export GBS_VOICE_API_KEY="$(gcloud secrets versions access latest --secret=gbs-voice-key-pai-pulse --project=adjudica-tools)"` (or the Key Vault equivalent) before launching the client.

## Live-call gating (ISC-89)

Reaching the service requires the consumer key to be on the gbs-voice
**shared allowlist** (per-consumer rate limits, contract §2). Until this MCP's
key (`gbs-voice-key-pai-pulse` or a dedicated `gbs-voice-key-mcp`) is appended
to that allowlist, live calls will `401`. The request **shape** is proven by
the mocked unit tests. Manual smoke once the key is provisioned:

```bash
# health (unauthenticated) — should return the provider readiness map
curl -s https://gbs-voice.wittycliff-d624a17c.westus2.azurecontainerapps.io/health
```

## Pulse drop-in HTTP shape (ISC-90)

PAI Pulse's voice handler (`PAI/PULSE/VoiceServer/voice.ts`) can call the same
service directly over HTTP instead of via stdio. The wire shapes are identical
to the tools above; the only Pulse-specific mapping is its 13 style presets →
the contract's `style` field on `POST /v1/audio/speech`:

```jsonc
// Pulse notify → gbs-voice speak
POST /v1/audio/speech
Authorization: Bearer <gbs-voice-key-pai-pulse>
Content-Type: application/json
{ "input": "Executing using PAI native mode",
  "voice": "gbs-default",       // or a named GBS voice
  "style": "focused",            // one of the 13 presets, provider-neutral
  "phi": false,                  // Pulse notifications carry no PHI
  "stream": false }
// → 200, audio/mpeg bytes; headers X-GBS-Voice-Provider, X-GBS-Voice-Fallback
```

## Development

```bash
npm install
npm run build     # tsc → build/  (Node ESM; moduleResolution NodeNext)
npm run lint      # tsc --noEmit (typechecks src + test)
npm test          # vitest run — mocked-fetch unit tests
```

> **Note on TypeScript config:** this package uses `module`/`moduleResolution:
> NodeNext` (not `bundler` like older sibling servers). The `@modelcontextprotocol/sdk`
> ≥ 1.29 `exports` map serves declaration files through conditions that only
> resolve correctly under NodeNext; `bundler` silently fails to find the SDK's
> `.d.ts` files.

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
