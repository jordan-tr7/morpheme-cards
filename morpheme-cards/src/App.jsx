import { useState, useRef, useCallback } from 'react'


// ---- Sample data — swap in your real morpheme set ----
const MORPHEMES = [
  { id: 'un', text: 'un', type: 'prefix' },
  { id: 're', text: 're', type: 'prefix' },
  { id: 'pre', text: 'pre', type: 'prefix' },
  { id: 'dis', text: 'dis', type: 'prefix' },
  { id: 'help', text: 'help', type: 'root' },
  { id: 'play', text: 'play', type: 'root' },
  { id: 'read', text: 'read', type: 'root' },
  { id: 'view', text: 'view', type: 'root' },
  { id: 'ful', text: 'ful', type: 'suffix' },
  { id: 'less', text: 'less', type: 'suffix' },
  { id: 'ing', text: 'ing', type: 'suffix' },
  { id: 'able', text: 'able', type: 'suffix' },
];
 
const TYPE_COLOR = {
  prefix: '#2B6777',
  root: '#C1543C',
  suffix: '#3C7A5C',
};
 
const CANVAS_W = 1600;
const CANVAS_H = 1200;
const MIN_ZOOM = 0.5;
const MAX_ZOOM = 2;
const LONG_PRESS_MS = 550; // touch: hold a card this long to remove it
const MOVE_THRESHOLD = 6; // px — below this, a touch is a tap/long-press, not a drag
 
const clamp = (v, min, max) => Math.min(max, Math.max(min, v));
 
let nextDropId = 1;



function App() {


 const [dropped, setDropped] = useState([]); // { dropId, id, text, type, x, y }
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [ghost, setGhost] = useState(null); // floating preview while dragging a new card in from the tray
  const [isPanning, setIsPanning] = useState(false);
 
  const viewportRef = useRef(null);
  const panState = useRef(null); // { lastX, lastY } while panning the board
  const cardGesture = useRef(null); // transient info for whichever card is being dragged / held
  const longPressTimer = useRef(null);
 
  // ---------- coordinate + pan helpers ----------
  const screenToWorld = useCallback((clientX, clientY) => {
    const rect = viewportRef.current.getBoundingClientRect();
    return {
      x: (clientX - rect.left - pan.x) / zoom,
      y: (clientY - rect.top - pan.y) / zoom,
    };
  }, [pan, zoom]);
 
  // No pan clamping — the board is meant to feel like an infinite whiteboard,
  // so you can drag away from the content in any direction indefinitely.
 
  const zoomAtCenter = (factor) => {
    setZoom((prevZoom) => {
      const newZoom = clamp(+(prevZoom * factor).toFixed(2), MIN_ZOOM, MAX_ZOOM);
      const rect = viewportRef.current.getBoundingClientRect();
      const cx = rect.width / 2;
      const cy = rect.height / 2;
      setPan((prevPan) => {
        const worldX = (cx - prevPan.x) / prevZoom;
        const worldY = (cy - prevPan.y) / prevZoom;
        return { x: cx - worldX * newZoom, y: cy - worldY * newZoom };
      });
      return newZoom;
    });
  };
 
  const resetView = () => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  };
 
  // ---------- panning the board: press-drag on empty space, mouse or touch ----------
  const onViewportPointerDown = (e) => {
    if (e.target.closest('[data-card]')) return; // let the card handle it instead
    viewportRef.current.setPointerCapture(e.pointerId);
    panState.current = { lastX: e.clientX, lastY: e.clientY };
    setIsPanning(true);
  };
 
  const onViewportPointerMove = (e) => {
    if (!panState.current) return;
    const dx = e.clientX - panState.current.lastX;
    const dy = e.clientY - panState.current.lastY;
    panState.current.lastX = e.clientX;
    panState.current.lastY = e.clientY;
    setPan((prev) => ({ x: prev.x + dx, y: prev.y + dy }));
  };
 
  const endViewportPan = () => {
    panState.current = null;
    setIsPanning(false);
  };
 
  // ---------- morpheme cards: drag from tray, reposition on board, tap-and-hold to remove ----------
  const clearLongPress = () => {
    if (longPressTimer.current) {
      clearTimeout(longPressTimer.current);
      longPressTimer.current = null;
    }
  };
 
  const beginCardPointer = (e, payload) => {
    e.stopPropagation();
    e.currentTarget.setPointerCapture(e.pointerId);
    cardGesture.current = {
      payload,
      pointerId: e.pointerId,
      startX: e.clientX,
      startY: e.clientY,
      moved: false,
    };
 
    if (payload.source === 'canvas') {
      const world = screenToWorld(e.clientX, e.clientY);
      cardGesture.current.grabDX = world.x - payload.x;
      cardGesture.current.grabDY = world.y - payload.y;
 
      // touch: holding still (no drag) for LONG_PRESS_MS removes the card
      if (e.pointerType === 'touch') {
        longPressTimer.current = setTimeout(() => {
          if (cardGesture.current && !cardGesture.current.moved) {
            removeCard(payload.dropId);
            cardGesture.current = null;
          }
        }, LONG_PRESS_MS);
      }
    } else {
      setGhost({ ...payload, clientX: e.clientX, clientY: e.clientY });
    }
  };
 
  const onCardPointerMove = (e) => {
    const g = cardGesture.current;
    if (!g || g.pointerId !== e.pointerId) return;
    const dist = Math.hypot(e.clientX - g.startX, e.clientY - g.startY);
    if (dist > MOVE_THRESHOLD) {
      g.moved = true;
      clearLongPress();
    }
 
    if (g.payload.source === 'tray') {
      setGhost({ ...g.payload, clientX: e.clientX, clientY: e.clientY });
    } else {
      const world = screenToWorld(e.clientX, e.clientY);
      const x = world.x - g.grabDX;
      const y = world.y - g.grabDY;
      setDropped((prev) =>
        prev.map((c) => (c.dropId === g.payload.dropId ? { ...c, x, y } : c))
      );
    }
  };
 
  const onCardPointerUp = (e) => {
    clearLongPress();
    const g = cardGesture.current;
    if (!g || g.pointerId !== e.pointerId) return;
    cardGesture.current = null;
 
    if (g.payload.source === 'tray') {
      if (g.moved) {
        const world = screenToWorld(e.clientX, e.clientY);
        const rect = viewportRef.current.getBoundingClientRect();
        const overBoard =
          e.clientX >= rect.left && e.clientX <= rect.right &&
          e.clientY >= rect.top && e.clientY <= rect.bottom;
        if (overBoard) {
          const { id, text, type } = g.payload;
          setDropped((prev) => [
            ...prev,
            { dropId: nextDropId++, id, text, type, x: world.x - 45, y: world.y - 26 },
          ]);
        }
      }
      setGhost(null);
    }
    // canvas-card case: position was already updated live during move; nothing more to do
  };
 
  const removeCard = (dropId) => {
    setDropped((prev) => prev.filter((c) => c.dropId !== dropId));
  };


  return (
        <div className="app">
      {/* LEFT — static panel */}
      <aside className="sidebar">
        <header className="header">
          <div className="logo-mark">+</div>
          <h1 className="title">Word Builder</h1>
          <p className="subtitle">Drag pieces onto the board</p>
        </header>
 
        <div className="tray-scroll">
          {['prefix', 'root', 'suffix'].map((group) => (
            <div key={group} className="tray-group">
              <p className="group-label" style={{ color: TYPE_COLOR[group] }}>
                {group === 'prefix' ? 'Starts' : group === 'root' ? 'Main words' : 'Endings'}
              </p>
              <div className="tray-grid">
                {MORPHEMES.filter((m) => m.type === group).map((m) => (
                  <div
                    key={m.id}
                    data-card
                    className="card"
                    onPointerDown={(e) => beginCardPointer(e, { source: 'tray', ...m })}
                    onPointerMove={onCardPointerMove}
                    onPointerUp={onCardPointerUp}
                    style={{ borderColor: TYPE_COLOR[m.type] }}
                  >
                    {m.text}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </aside>
 
      {/* RIGHT — the board */}
      <main className="board">
        <div className="zoom-bar">
          <button className="zoom-btn" onClick={() => zoomAtCenter(1 / 1.2)}>−</button>
          <span className="zoom-label">{Math.round(zoom * 100)}%</span>
          <button className="zoom-btn" onClick={() => zoomAtCenter(1.2)}>+</button>
          <button className="reset-btn" onClick={resetView}>Reset</button>
          <span className="hint">Drag empty space to move around · hold a card to remove it</span>
        </div>
 
        <div
          ref={viewportRef}
          className="viewport"
          style={{
            backgroundPosition: `${pan.x}px ${pan.y}px`,
            backgroundSize: `${32 * zoom}px ${32 * zoom}px`,
            cursor: isPanning ? 'grabbing' : 'grab',
          }}
          onPointerDown={onViewportPointerDown}
          onPointerMove={onViewportPointerMove}
          onPointerUp={endViewportPan}
          onPointerCancel={endViewportPan}
        >
          <div
            className="canvas"
            style={{
              width: CANVAS_W,
              height: CANVAS_H,
              transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
            }}
          >
            {dropped.length === 0 && (
              <p className="empty-hint">Drag word pieces here to build words</p>
            )}
            {dropped.map((card) => (
              <div
                key={card.dropId}
                data-card
                className="placed-card"
                onPointerDown={(e) => beginCardPointer(e, { source: 'canvas', ...card })}
                onPointerMove={onCardPointerMove}
                onPointerUp={onCardPointerUp}
                onDoubleClick={() => removeCard(card.dropId)}
                style={{
                  left: card.x,
                  top: card.y,
                  borderColor: TYPE_COLOR[card.type],
                }}
                title="Double-click (or hold on touch) to remove"
              >
                {card.text}
              </div>
            ))}
          </div>
        </div>
      </main>
 
      {/* floating preview while dragging a new card in from the tray */}
      {ghost && (
        <div
          className="ghost"
          style={{ left: ghost.clientX, top: ghost.clientY, borderColor: TYPE_COLOR[ghost.type] }}
        >
          {ghost.text}
        </div>
      )}
    </div>

  )
}

export default App
