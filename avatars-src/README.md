# New faces

Synthetic portraits (people who do not exist, generated with xAI `grok-imagine-image`) ready to be turned
into LAM 3D heads. LAM needs a CUDA GPU, so conversion happens outside this Mac:

**Option A — ModelScope demo (free, ~2 min per face).**
1. Open https://www.modelscope.cn/studios/Damo_XR_Lab/LAM_Large_Avatar_Model (log in).
2. Upload a portrait, enable the export for OpenAvatarChat, generate, download the `.zip`.
3. Save it as `server/src/handlers/client/ws_lam_client/lam_samples/<name>.zip` (lowercase name, e.g. `maya.zip`).
4. Add `{ id: '<name>', label: '<Label>', preview: 'avatars/<name>.jpg' }` to `web/src/config/companion.ts`
   and run `scripts/make_preview.sh <name>` to create the thumbnail.

**Option B — automate it.** Give Claude a ModelScope access token (modelscope.cn → Account → Access Token)
and it can call the same demo through its API.

**Option D — Google Colab (free GPU, all portraits at once).** Open
https://colab.research.google.com/github/AmanYadav007/bwithu/blob/main/avatars-src/make_faces_colab.ipynb,
set Runtime → T4 GPU, Run all (~30–40 min the first time). It downloads `bwithu_faces.zip` with one
`<name>.zip` per portrait; then do steps 3–4 of Option A for each.

**Option C — rent a GPU for an hour** (RunPod/Modal/Lambda) and run LAM's `tools/AVATAR_EXPORT_GUIDE.md`.
