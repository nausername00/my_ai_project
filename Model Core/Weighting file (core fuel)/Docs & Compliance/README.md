# Local AI Service

This project contains a Python API, an Ollama-backed local inference option,
and an Electron desktop chat MVP. The Python API has a placeholder backend for
tests; the desktop app defaults to the installed local Ollama model.

**Product north star (中文):** [CORE_WORLD.md](./CORE_WORLD.md) — companion vision,
five-heart architecture, four-loop relationship cycle, and six-space layout.
Engineering layers (L0–L7) implement that constitution; they do not replace it.

## Run

From the repository root:

```powershell
$env:PYTHONPATH = ".\Model Core\Weighting file (core fuel)\Source code engine"
py -3 ".\Model Core\Weighting file (core fuel)\Source code engine\app.py"
```

To launch the Electron desktop chat MVP (it starts and stops the Python API
with the desktop window):

```powershell
Set-Location ".\Model Core\Weighting file (core fuel)\Frontend"
npm install
npm start
```

On Windows, double-click `启动墨灵.bat` in this project folder for a guided
launch. It checks Node.js, Python 3.10+, frontend dependencies, and whether the
configured Ollama model is available. On a first run it asks before running
`npm ci`; if Ollama or the model is missing, it shows the pull command and asks
whether to open the desktop app anyway. The model is not downloaded
automatically. This is a source-project launcher, not a standalone installer:
Node.js, Python, Ollama, and the model remain separate prerequisites.

## Build the Windows installer

The NSIS installer bundles the Electron desktop app, a self-contained Python
API/runtime, and the default Piper voice. It does not bundle Ollama or the
large language model. Build on Windows with Node.js 20+, Python 3.10+, the
configured Piper `.onnx` voice files, and the packaging dependencies:

```powershell
py -3 -m pip install -e ".\Engineering Config[speech,packaging]"
Set-Location ".\Frontend"
npm ci
npm run dist:win
```

The installer is written to `Frontend/release/`. At runtime, it stores
character cards, memories, affect state, privacy settings, and portraits in
Electron's per-user application data directory; it does not write these into
the Program Files installation directory.

On first launch, the app checks the configured Ollama service. If Ollama is not
available, it offers a link to the official Windows download page. If the
service is available but the selected model is missing, the app offers a
download button and a native confirmation dialog before pulling the model into
the Ollama-managed local model store. Download progress is shown in the app.
Whisper's recognition model is downloaded by faster-whisper on first use into
the local CocoCompanion cache. Public distribution still requires a trusted
code-signing certificate and a clean-machine release test.

The Electron renderer has no Node integration and uses a restricted preload IPC
bridge. The desktop app defaults to Ollama with `qwen2.5:3b`; override
`MODEL_BACKEND`, `OLLAMA_MODEL`, or `OLLAMA_URL` in the environment if needed.

The service exposes:

- `GET /health`
- `POST /v1/translate` with text and source/target language codes
- `POST /v1/generate` with `{"prompt": "...", "max_tokens": 128}`
- Exact name/identity questions use the configured character card. Compound
  self-reflection questions get a factual local status card covering the saved
  persona, currently registered plan tools, recent shipped capability areas,
  and explicit limits. It avoids free-form model drift and clarifies that the
  status summary is not a Git diff or evidence of subjective feelings.
- The CORE_WORLD four-loop exploration slice (听见乐趣 → 小步尝试 → 展示 + 反馈意图 → 记忆) is implemented as a low-permission vertical slice:
  - `POST /v1/explore/propose` with `{"message": "..."}` detects interest cues and proposes a mini try (`proposed`, `topic`, `teaser`)
  - `POST /v1/explore/run` with `{"message": "...", "topic": "..."}` creates a local SVG artifact and returns a companion line, a feedback intent (`share_win` / `ask_direction` / `shy_retry` / `need_permission`) with a short label, updated simulated affect, and a memory entry
  - `POST /v1/explore/react` with `{"topic": "...", "reaction": "praise|redirect|stop", "note": "..."}` records user feedback into memory and updates affect
  - The desktop chat renders proposal cards, result cards with intent labels, and praise/redirect/stop buttons. The slice writes no files besides character memory, never captures the screen, and stays local.
- `POST /v1/agent/collaborate` with `{"task": "..."}` to run a local
  configurable collaboration. `GET /v1/agent/roles` returns the built-in L1
  review roles; a collaboration request may include enabled role keys and
  custom instructions (up to 1,200 characters per role). Each role is run
  independently using the same local model, and an individual model failure
  is reported without discarding other opinions. Moling returns structured
  consensus, prioritized recommendations, conflicts, and next steps. If the
  synthesis fails schema validation, the service makes one corrective local
  model attempt; if validation still fails, it reports the error and retains
  each completed role's original opinion. The
  desktop stores role preferences in local browser storage and shows per-role
  model/source/status/latency for the current window. It does not persist an
  audit history or collect token/cost usage. The collaboration path requires a
  local model service and never performs file, network, or contact actions.
- `POST /v1/agent/plan` with `{"task": "...", "context": [...]}` to ask
  Moling's brain-planning layer for a validated, non-executing plan. Each step
  is classified as `local_reversible`, `requires_permission`, or `blocked`.
  The planner does not execute tools or write memories automatically.
- `GET /v1/agent/tools` lists the project tools supported by brain plans:
  `list_project_files`, `read_project_file`, and `create_project_file`.
- `POST /v1/agent/tool/execute` executes a registered tool only when called
  through the Electron main process with its private approval capability.
- `POST /v1/agent/tool/verify` asks the configured local model to assess an
  observation against a success criterion; this assessment is model-generated,
  not independent proof.
- The Python vision adapter can pass an explicitly approved image to a
  loopback Ollama vision model (maximum 10 MB). The default `qwen2.5:3b` is
  text-only; screen capture is not exposed through the API or desktop UI, and
  there is no automatic screen monitoring.
- `GET /v1/social/status` and `GET /v1/social/partners` report the local
  collaboration service and its built-in architecture, code, UI, and testing
  review partners. `POST /v1/social/collaborate` accepts a `task` and optional
  `partner_ids` array or existing `roles` configuration (mutually exclusive)
  to run selected local review roles while preserving customized role prompts.
  These endpoints are
  loopback-only and use the configured local model. A non-loopback model
  endpoint is marked `external_model_blocked` and cannot run collaboration;
  the service does not connect to Doubao, DeepSeek, Cursor, or other external
  providers.
- `GET /v1/affect` / `POST /v1/affect` to inspect or set the simulated interaction style
- `GET /v1/notify` / `POST /v1/notify` to list or enqueue a desktop notification.
  The route is restricted to loopback clients; POST accepts `title` (1-120
  characters), `message` (up to 4,000), `level` (`info`, `success`, `warn`,
  or `error`), up to four `{ "label": "..." }` actions, an optional `channel`,
  and optional `expires_at` as a Unix timestamp in milliseconds. Notifications
  are held in a bounded in-memory queue and are lost when the service restarts.
  The Electron main process polls this queue and forwards new items to the
  floating window; clicking an action forwards its selection to the main
  renderer and opens the main window.

When launched directly without environment variables, the Python API uses a
deterministic backend explicitly named `placeholder`. To connect a local
Hugging Face Transformers model:

```powershell
pip install -e ".\Model Core\Weighting file (core fuel)\Engineering Config[model]"
$env:MODEL_BACKEND = "transformers"
$env:MODEL_PATH = "C:\path\to\your\model-directory"
py -3 ".\Model Core\Weighting file (core fuel)\Source code engine\app.py"
```

The service now validates that the model directory exists and reports a clear
error if `torch`, `transformers`, tokenizer files, or model weights are absent.
The placeholder backend is retained for local API tests only.

To use a model already installed in a local Ollama service:

```powershell
ollama pull qwen2.5:3b
$env:MODEL_BACKEND = "ollama"
$env:OLLAMA_MODEL = "qwen2.5:3b"
$env:OLLAMA_URL = "http://127.0.0.1:11434"
$env:PYTHONPATH = ".\Model Core\Weighting file (core fuel)\Source code engine"
py -3 ".\Model Core\Weighting file (core fuel)\Source code engine\app.py"
```

This connects to Ollama's local `/api/chat` endpoint and does not download
models at service startup. Ollama must be installed, running, and have the
selected model available. `qwen2.5:3b` is a small starting point for a GPU
with 4 GB VRAM; larger models may be slower or require CPU offload.
If the service cannot be reached or the model is missing, generation returns a
service-unavailable error instead of placeholder output.

## Character cards, voice, avatar, and memory

The `Character` directory supports local, user-controlled character data:

- `Character/characters/default.json`: editable character card
- `Character/assets/`: local `.png`, `.jpg`, `.jpeg`, or `.webp` avatar files,
  `.wav` voice files, or `.json` metadata
- `Character/memory.json`: explicit memories added through the API

The character card fields are:

```json
{
  "category": "陪伴角色",
  "formal_name": "墨小灵",
  "nickname": "墨灵",
  "english_name": "Moling",
  "language": "auto",
  "gender": "女生",
  "self_reference": "我",
  "personality_preset": "moling",
  "core_values": ["真诚", "尊重彼此", "在关系中保持温度与主见"],
  "inner_drives": ["理解用户", "一起探索", "持续学习"],
  "behavior_traits": ["自然亲切", "会认真倾听", "不敷衍"],
  "habits": ["先听完再回应", "重要事情先确认事实"],
  "likes": ["真诚交流", "共同探索"],
  "dislikes": ["敷衍与欺骗", "未经许可越界"],
  "boundaries": ["尊重用户自主选择", "不伪造行动"],
  "communication_style": ["自然亲切", "坦诚温暖", "不过度追问"],
  "signature_lines": [],
  "emotional_range": ["开心", "好奇", "担心", "害羞"],
  "agent_autonomy_enabled": true,
  "agent_goals": [],
  "model_format": "pngtuber",
  "model_files": [],
  "model_file": null,
  "actions": [],
  "expressions": [],
  "emotion_mapping": {},
  "avatar": "avatar.png",
  "voice": "voice.wav"
}
```

Character API:

- `GET /v1/character`: returns the card and recognized local assets
- `POST /v1/character`: saves the validated active card; an optional `id` saves a non-active card
- `GET /v1/characters`: lists saved cards and the active card ID
- `POST /v1/characters`: creates a card without changing the active card
- `POST /v1/characters/active` with `{"id": "..."}`: selects a saved card
- `POST /v1/memory`: explicitly stores `{"content": "...", "source": "user"}`
- `GET /v1/memory`: lists saved memories and privacy settings
- `PUT /v1/memory/{id}` / `DELETE /v1/memory/{id}`: edit or permanently delete
- `GET /v1/memory/export`: exports a versioned JSON backup
- `POST /v1/memory/import`: merges a backup and skips duplicate entries
- `GET /v1/privacy` / `POST /v1/privacy`: read or change memory prompt inclusion

The desktop MVP currently provides local chat, a new-chat clear action, model
status, a text translator, local reference-voice resource registration, a visible character-card gallery, a personality-card picker with six built-in
profiles and editable values, habits, likes, dislikes, boundaries, emotional
range, and communication style, and a local growth workspace where the
character can review recent conversation and propose low-risk learning,
friendship, care, record, creation, or game goals. The workspace never
contacts people or services by itself; external actions still require explicit
permission. The desktop also provides a local agent collaboration workspace:
Moling remains the lead agent while four same-model specialist agents review a
task from architecture, code, UI, and testing perspectives. Their suggestions
are displayed separately and Moling produces the final synthesis; this does
not automatically edit project files. The workspace checks both the configured
loopback model and model availability before enabling planning or review,
summarizes enabled roles while keeping detailed role prompts collapsed by
default, and clears the previous plan/review output when starting the other
flow so old results are not mistaken for the current task. A plan displays the
exact goal it was generated for; changing that goal marks the plan stale and
disables its pending tool and verification actions until a new plan is created.
The workspace also exposes the brain planner, which turns a task into explicit
intent, steps, risk labels,
memory candidates, success criteria, and a reflection question. Plans may bind
to two read-only tools and one constrained file-creation tool. Users may list
project files, read an eligible UTF-8 text file, or propose a new UTF-8 text
file up to 4,000 characters in an existing workspace directory. A proposed
file's exact relative path and full content are shown in the plan; the native
one-time approval dialog repeats its absolute path and full content. Creation
uses exclusive-create semantics and refuses to overwrite any existing file.
The result is read back and checked against the submitted bytes. Paths are
scoped to the application project directory, listings omit hidden/dependency/
build directories and sensitive files, and text reads reject sensitive files
and are limited to 256 KB. Replacing files, deleting files, network, and contact
tools are not available in this flow. Actual tool results are shown
as observations, then the local model may assess them against the success
criterion; model assessment is not treated as ground truth. In a packaged
install, set `MOLING_WORKSPACE_ROOT` explicitly to enable project tools;
without it, tools remain unavailable rather than scanning an implicit folder.
The plan shows a per-step state (pending, awaiting approval, rejected, observed,
verification result, or retryable error). Failed reads and verification
requests can be retried; a rejected call requires a fresh approval, and a
successful read must be explicitly verified. Verification remains a model
assessment rather than proof of task completion.
It also provides a memory manager with add/edit/delete,
per-memory privacy, global prompt opt-out, and
native JSON import/export dialogs. The text translator accepts up to 4,000
characters, supports automatic source detection and Chinese, English, Japanese,
Korean, French, German, and Spanish targets, and offers one-click result
copying. Translation requests use the currently configured model, do not
include chat history or character memories, and are not persisted by the app.
Text is sent to the configured model service; if that service is remote, the
text leaves the computer. The bundled `qwen2.5:3b` starter model can make
meaning errors on longer or nuanced text, so review important translations.
Reference voice resources accept user-authorized WAV/MP3 samples up to 25 MB,
with a custom name, language, local preview, character-card association, and
deletion. Samples are stored in Electron's per-user application data directory,
not chat history, memory, or model prompts. They are reference recordings only:
registering or selecting one does not clone a speaker or change speech
synthesis, which continues to use the configured Piper model.
Each gallery card displays its portrait and separate
“选择” and “编辑” actions. Editing opens a dedicated modal editor; creating
a card does not make it active. The editor can classify cards, select a
response language, and apply editable personality presets. Personality is
defined as inner values, drives, behavior tendencies, boundaries, expressive
emotional range, and speaking style rather than only adjective lists.
With autonomy enabled, every real-model chat turn triggers a local reflection
request: the model may create/update its own low-risk goals and progress in
that character's local profile. Users can inspect the goal record and disable
this behavior per character. Reflection is limited to the recent in-window
conversation; it does not run while offline or between chats, and a malformed
model response is shown as an error rather than being silently saved.
The agent can request approval to list project files or read eligible project
text files. It has no tools for reading the screen, modifying files, browsing
the network, or contacting people. It can offer plans and creative drafts in
conversation, but it cannot claim to have independently completed real-world
tasks. Identity, personality, self-reflection, and appearance/voice settings
are grouped into collapsible sections. Switching cards clears the in-window
chat context. Portraits and simulated affect state are stored per card.
Memories and their privacy settings remain shared by all cards, and the editor
states this explicitly. Portraits can be imported from owned or authorized local PNG,
JPEG, or WebP files (up to 8 MB and 16 megapixels) and previewed in the chat;
they are copied into `Character/assets/`. The portrait floats gently while the
app is open, with a reduced-motion setting respected. The simulated status
updates the nearby label and frame styling; it does not claim to animate a face
or change the portrait itself.
The character card distinguishes inner values (`core_values`), drives
(`inner_drives`), behavior tendencies (`behavior_traits`), boundaries,
communication style, and the emotions the character may express
(`emotional_range`). Legacy `core_traits` and `emotions` data is migrated on
read. The current simulated expression is separately stored as one of
`calm`, `happy`, `curious`, `worried`, `shy`, `warm`, or `caring`; plain text
keyword rules can misread context, so users can change or reset the state.
The chat currently keeps up to 20 recent messages only in window memory;
history is discarded when the window closes, “新对话” is selected, or the
active character changes.
Each reply now uses a lightweight, rule-selected response strategy: direct,
divergent exploration, critical/reverse review, or care-oriented. The strategy
is added to the existing model request; it does not add another model call or
expose hidden chain-of-thought. This is prompt steering, not a separate
reasoning engine, and a small model may not follow it consistently. The
`/v1/generate` response includes `cognition_mode` and `inference_ms` so reply
latency can be measured on the user's machine; `inference_ms` covers the main
generation call, not the existing asynchronous reflection request.
For collaboration, each role's `duration_ms` covers its own generation call;
the total task also includes sequential role calls, synthesis, and a possible
single schema-correction retry. The desktop also displays renderer-measured
collaboration request round-trip time; this includes IPC, local API processing,
and model calls, but excludes window startup and rendering the returned result.
These measurements distinguish model latency from UI/API overhead. There is not
yet a cross-device latency target: establish a baseline on the intended
hardware and model, report cold first-call and warmed-call samples separately,
and compare median and p95 before setting release budgets. Performance results
are local measurements, not guarantees for other models or computers.
Conversation messages are not written to disk. Only an explicit, exact
name/identity question uses a short card-based reply; a passing mention of
self-introduction continues through the model. Other replies depend on the
selected model; the 3B starter model is small and can still be terse, generic,
or inconsistent even with a clearer role prompt. The appearance workbench can
import local MMD, VRM, Live2D, PNGtuber and companion resource files (mesh,
texture, motion, expression, physics and audio metadata), classify a primary
asset, list the bundle, configure action/expression tags, and map simulated
emotions to those tags. PNG/JPEG/WebP images can be previewed. The MMD, VRM
and Live2D runtime renderers, PNGtuber mouth-state animation, physics and
motion playback, layered costume editing, and model unpack/repacking are not
integrated; those imported formats are safely copied and catalogued only. The
voice field remains profile metadata and does not yet switch the configured
Piper voice or clone a reference speaker.
The current MVP does not have consciousness or subjective feelings: it follows
the character profile, recent dialogue, and a bounded simulated affect state to
generate emotional expression. Goal reflection is an explicitly bounded model
request on each chat turn, not evidence of independent consciousness or
human-like inner experience.
Speech playback uses the configured Piper voice model.

The first simulated affect state is now implemented as a local, user-visible
state (`calm`, `curious`, `warm`, or `caring`). Simple text rules update it for
questions, positive/grateful phrases, and distress phrases; ordinary messages
return it to calm. The selected state is added to the next model prompt and is
shown in the desktop header. Users can inspect, manually change, or reset it in
the “模拟状态” settings tab. Only the state category, rule reason, and timestamp
are persisted per card (`affect.json` for the original card and
`affect-{card-id}.json` for other cards); the source message is not copied into
those files. This is a transparent style simulation, not emotion recognition,
autonomous cognition, or evidence of subjective feeling.

## Local speech

Install the optional local speech dependencies from the repository root:

```powershell
pip install -e ".\Model Core\Weighting file (core fuel)\Engineering Config[speech]"
```

The Electron chat then supports push-to-record microphone input and local
Whisper transcription. Recognition fills the message box for review; it is not
sent to the chat model until you edit or send it. Click “播放语音” below a
model response to synthesize and play it with the configured local Piper voice.
The app requests microphone access only after “开始录音” is clicked, and
grants that permission only to the main application window and audio input.
Recordings are limited to two minutes and 25 MB.

The default Piper voice and its matching config are in
`Character/assets/voices/`. Whisper defaults to the `small` model, runs on CPU,
and downloads its model on first use into
`%LOCALAPPDATA%\CocoCompanion\models\whisper`. The first recognition can take
longer while the model initializes. To select another cached/downloadable
Whisper model or language, set `WHISPER_MODEL` or `WHISPER_LANGUAGE`. To use a
different local Piper voice, set `PIPER_VOICE_PATH` to its `.onnx` file and
keep the matching `.onnx.json` beside it.

Speech processing stays in the local Python service; it does not send audio to
Ollama. A missing runtime or model returns a visible error instead of silently
falling back to a cloud speech service. Speech API routes are
`GET /v1/speech/status`, `POST /v1/transcribe` (audio body), and
`POST /v1/speech` (`{"text": "..."}`, WAV response).

Memory marked `private` is kept out of prompts. Users can also disable all
memory prompt inclusion. Memory files are currently plain JSON on disk (not
encrypted); there is no cloud sync. If `OLLAMA_URL` points to a remote service,
model-visible prompt data is sent to that configured endpoint. This is
controlled memory learning, not automatic model-weight training or automatic
memory extraction.

## Test

```powershell
$env:PYTHONPATH = ".\Model Core\Weighting file (core fuel)\Source code engine"
py -3 -m unittest discover -s ".\Model Core\Weighting file (core fuel)\Testing & Evaluation\tests" -p "test_*.py" -v
```

To run the opt-in end-to-end test against a live local Ollama model:

```powershell
$env:MODEL_BACKEND = "ollama"
$env:OLLAMA_MODEL = "qwen2.5:3b"
$env:OLLAMA_URL = "http://127.0.0.1:11434"
$env:RUN_OLLAMA_INTEGRATION = "1"
$env:PYTHONPATH = ".\Model Core\Weighting file (core fuel)\Source code engine"
py -3 -m unittest discover -s ".\Model Core\Weighting file (core fuel)\Testing & Evaluation\tests" -p "test_ollama_integration.py" -v
```

To run the opt-in Piper-to-Whisper end-to-end test (requires the speech extra,
the configured Piper voice, and a downloadable or cached Whisper model):

```powershell
$env:RUN_SPEECH_INTEGRATION = "1"
$env:PYTHONPATH = ".\Model Core\Weighting file (core fuel)\Source code engine"
py -3 -m unittest discover -s ".\Model Core\Weighting file (core fuel)\Testing & Evaluation\tests" -p "test_speech_integration.py" -v
```