const express = require('express');
const http = require('http');
const cors = require('cors');
const jwt = require('jsonwebtoken');
const { Server } = require('socket.io');

const app = express();
const server = http.createServer(app);
const io = new Server(server, { cors: { origin: '*' } });

const PORT = Number(process.env.PORT || 3001);
const JWT_SECRET = process.env.JWT_SECRET || 'dev-secret';
const EDGE_WEBHOOK_TOKEN = process.env.EDGE_WEBHOOK_TOKEN || 'edge-webhook-token';

app.use(cors());
app.use(express.json({ limit: '8mb' }));

const cameras = [];
const violations = [];

function requireAuth(req, res, next) {
  const auth = String(req.headers.authorization || '');
  const token = auth.startsWith('Bearer ') ? auth.slice(7) : '';
  if (!token) return res.status(401).json({ ok: false, error: 'Missing token' });
  try {
    req.user = jwt.verify(token, JWT_SECRET);
    next();
  } catch {
    return res.status(401).json({ ok: false, error: 'Invalid token' });
  }
}

function requireEdgeToken(req, res, next) {
  const token = String(req.headers['x-edge-token'] || '');
  if (token !== EDGE_WEBHOOK_TOKEN) return res.status(401).json({ ok: false, error: 'Invalid edge token' });
  next();
}

app.get('/api/health', (_req, res) => {
  res.json({ ok: true, service: 'node-api', ts: Date.now() });
});

app.post('/api/auth/dev-token', (req, res) => {
  const username = String(req.body?.username || 'operator');
  const role = String(req.body?.role || 'admin');
  const token = jwt.sign({ username, role }, JWT_SECRET, { expiresIn: '12h' });
  res.json({ ok: true, token });
});

app.get('/api/cameras', requireAuth, (_req, res) => {
  res.json({ ok: true, cameras });
});

app.post('/api/cameras', requireAuth, (req, res) => {
  const id = `cam-${Date.now()}`;
  const cam = {
    id,
    name: String(req.body?.name || id),
    url: String(req.body?.url || ''),
    online: true,
    createdAt: new Date().toISOString(),
  };
  cameras.push(cam);
  io.emit('camera-added', cam);
  res.json({ ok: true, camera: cam });
});

app.delete('/api/cameras/:id', requireAuth, (req, res) => {
  const idx = cameras.findIndex(c => c.id === req.params.id);
  if (idx === -1) return res.status(404).json({ ok: false, error: 'Camera not found' });
  const [deleted] = cameras.splice(idx, 1);
  io.emit('camera-removed', deleted);
  res.json({ ok: true });
});

app.get('/api/violations', requireAuth, (_req, res) => {
  res.json({ ok: true, violations });
});

app.post('/api/ai-violation', requireEdgeToken, (req, res) => {
  const payload = {
    id: `vio-${Date.now()}`,
    type: String(req.body?.type || 'unknown'),
    confidence: Number(req.body?.conf || req.body?.confidence || 0),
    plate: String(req.body?.plate || 'unknown'),
    lat: Number(req.body?.lat || 0),
    lng: Number(req.body?.lng || 0),
    image: req.body?.image || null,
    ts: new Date().toISOString(),
  };
  violations.unshift(payload);
  if (violations.length > 10000) violations.length = 10000;
  io.emit('violation', payload);
  res.json({ ok: true, id: payload.id });
});

io.on('connection', (socket) => {
  socket.emit('bootstrap', { cameras, violations: violations.slice(0, 50) });
  socket.on('add-camera', (data) => {
    const cam = {
      id: `cam-${Date.now()}`,
      name: String(data?.name || 'camera'),
      url: String(data?.url || ''),
      online: true,
      createdAt: new Date().toISOString(),
    };
    cameras.push(cam);
    io.emit('camera-added', cam);
  });
});

server.listen(PORT, () => {
  console.log(`[node-api] listening on :${PORT}`);
});
