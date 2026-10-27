# Vercel Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy neuroSim's Next.js frontend and FastAPI mock-data backend together as one production Vercel project linked to `wiwiwashere/neuroSim`.

**Architecture:** Keep the existing local two-process workflow intact. Use `frontend/` as Vercel's project root, add a Python entry point there that exposes the existing FastAPI `app` from the repository-level backend, route `/api/*` to the Python function, and disable the localhost Next.js proxy only during Vercel builds.

**Tech Stack:** Vercel, Next.js 15, React 19, FastAPI, Python 3.11+

**Spec:** `CLAUDE.md` and the user's request to deploy `https://github.com/wiwiwashere/neuroSim` through Vercel.

## Global Constraints

- Preserve local development: Next.js continues proxying `/api/*` to `NEUROSIM_API_URL` outside Vercel.
- Deploy without secrets; the LLM-only features may report that `GEMINI_API_KEY` is unavailable.
- Use the committed mock API payloads because the 852 MB FlyWire dataset is intentionally not in Git.
- Do not push without explicit approval.

---

### Task 1: Add the Vercel application boundary

**Files:**
- Create: `frontend/api/index.py`
- Create: `frontend/requirements.txt`
- Create: `frontend/vercel.json`
- Modify: `frontend/next.config.ts`
- Test: `tests/test_vercel_deployment.py`

**Interfaces:**
- Consumes: `backend/neurosim/api/main.py:app`
- Produces: an ASGI entry point at `frontend/api/index.py:app` and a same-origin `/api/*` route

- [ ] **Step 1: Write deployment-contract tests**

Verify that `frontend/api/index.py` exports the existing FastAPI application, `frontend/vercel.json` builds `.next`, and the frontend omits its localhost rewrite when `VERCEL=1`.

- [ ] **Step 2: Run the focused test and confirm it fails**

Run: `python -m pytest tests/test_vercel_deployment.py -q`
Expected: FAIL because the deployment files do not exist.

- [ ] **Step 3: Implement the minimal Vercel adapter**

Create a small Python import adapter, a Vercel build/routing configuration, and a conditional Next.js rewrite.

- [ ] **Step 4: Run focused and existing verification**

Run: `python -m pytest tests/test_vercel_deployment.py -q`
Run: `cd frontend && npm install && npm run typecheck && npm run build`
Expected: all commands succeed.

### Task 2: Link and release the Git repository

**Files:**
- No additional repository files.

**Interfaces:**
- Consumes: GitHub branch `main` and the Vercel team `winnie-lins-projects`
- Produces: a Git-linked Vercel project and production deployment URL

- [ ] **Step 1: Request approval before pushing**

Show the exact changed files and request the repository-required push approval.

- [ ] **Step 2: Commit and push the reviewed deployment adapter**

Run: `git add frontend/api/index.py frontend/requirements.txt frontend/vercel.json frontend/next.config.ts tests/test_vercel_deployment.py docs/superpowers/plans/2026-10-26-vercel-deployment.md`
Run: `git commit -m "chore: configure Vercel deployment"`
Run: `git push origin main`

- [ ] **Step 3: Create or reuse the Vercel Git project**

Link `wiwiwashere/neuroSim` to the authorized team with repository root `/`, then deploy the pushed `main` revision to production.

- [ ] **Step 4: Verify the live application**

Check deployment state and build logs, request `/`, and request `/api/diseases`. Expected: the homepage returns HTML and the API returns a JSON disease list.
