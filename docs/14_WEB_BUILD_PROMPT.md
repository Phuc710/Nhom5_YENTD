# Prompt Build Web Monitoring

Use this prompt when you want an AI coding assistant to extend or rebuild the web dashboard for this project.

## Prompt

You are a senior frontend engineer building a production-style monitoring dashboard for a traffic violation system.

Project context:

- Backend is FastAPI.
- Camera devices are ESP32-S3.
- Video flow is: ESP32 stream -> backend proxy/AI -> web.
- Backend is the single integration point. The web must not talk directly to ESP32, ThingsBoard, or Supabase.
- Database schema centers around `cameras`, `camera_provisioning`, `detection_zones`, `violations`, plus views like `view_camera_summary` and `view_violations_full`.
- The backend already exposes REST + SSE endpoints.

Backend contracts to use:

- `GET /api/dashboard/overview`
- `GET /api/dashboard/cameras`
- `GET /api/dashboard/recent-violations`
- `GET /api/violations`
- `GET /api/realtime/status`
- `GET /api/realtime/stream` for global SSE updates
- `GET /api/cameras/{camera_id}/stream` for backend-proxied live video
- `GET /api/cameras/{camera_id}/snapshot` for lightweight preview cards
- `GET /api/cameras/{camera_id}/live-view/sse` for selected camera overlay/detection updates
- `POST /api/cameras/{camera_id}/traffic-light`

Hard requirements:

1. The frontend must run independently from the backend.
2. If backend is offline, the UI must still open, show degraded state, and auto-reconnect when backend comes back.
3. Use retry with backoff for all SSE connections.
4. Do not open full MJPEG streams for every camera card.
5. Use snapshot previews for the grid, and only open the full stream for the selected camera.
6. Show clear connection badges for:
   - backend health
   - global realtime SSE
   - selected camera live-view SSE
7. The UI must support traffic-light control from web to backend.
8. The design should feel like a real monitoring console, not a generic admin template.

UI requirements:

- Sidebar layout with sections:
  - Live Monitoring
  - Recent Violations
  - Camera Grid
  - Violation Logs
  - System Connection State
- Main monitoring area:
  - selected camera large stream
  - overlay boxes for detections from live-view SSE
  - current traffic light state
  - selected camera metadata
  - latest violation for that camera
- Camera grid:
  - one card per camera
  - snapshot image
  - online/offline badge
  - violations today
  - violations total
- Recent violations feed:
  - prepend newest items
  - show license plate, camera name, timestamp, image thumbnail if available
- Violation log table:
  - camera filter
  - date range filter
  - confidence
  - image link

Tech constraints:

- Prefer plain HTML/CSS/JS or React if explicitly requested.
- Keep code modular.
- Centralize API paths and SSE logic.
- Cache the last successful payload in local storage so the UI still shows the last known state after refresh.
- Keep mobile usable, but prioritize desktop monitoring screens.

Behavior notes:

- The backend can be restarted independently.
- The frontend can be restarted independently.
- The web should never assume startup order.
- When realtime disconnects, fall back to polling.
- When reconnect succeeds, refresh overview, cameras, recent violations, and violations list.

If you generate code:

- Start with folder structure.
- Then create API helpers.
- Then create SSE/reconnect utilities.
- Then build the dashboard layout.
- Then wire traffic-light control.
- Then add empty/loading/offline states.

Output expectation:

- Clean, maintainable code.
- No mock endpoints.
- No direct database access from frontend.
- Use the exact backend contracts above unless I ask to change them.
