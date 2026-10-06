import { useState, useRef, useCallback } from 'react'
import LoginForm from './LoginForm';
import MORPHEMES from './data/updated_cards.json'


const LEVELS = [...new Set(MORPHEMES.map((m) => m.level))].sort();
const UNITS_BY_LEVEL = LEVELS.reduce((acc, level) => {
  acc[level] = [... new Set(
    MORPHEMES.filter((m) => m.level === level).map((m) => m.unit)
  )].sort();
  return acc;
}, {});

const getLessons = (m) => m.Lesson ?? ['All'];

const LESSONS = (() => {
  const set = new Set();
  MORPHEMES.forEach((m) => getLessons(m).forEach((lesson) => set.add(lesson)));
  const rest = [...set].filter((l) => l !== 'All').sort();
  return ['All', ...rest];
})();

const WORD_TYPES = [
  "prefix", "root", "base", "suffix"
]
 
const TYPE_COLOR = {
  'prefix': '#000',
  'root': '#000',
  'base': '#000',
  'suffix': '#000',
};

const ORIGIN_COLOR = {
  'Anglo-Saxon': '#429c21',
  'Latin': '#ff1c4d', 
  'Greek': '#000080'
}
 
const CANVAS_W = 1600;
const CANVAS_H = 1200;
const CARD_W = 160;
const CARD_H = 160;
const SNAP_THRESHOLD = 24;
const MIN_ZOOM = 0.5;
const MAX_ZOOM = 2;
const LONG_PRESS_MS = 550; // touch: hold a card this long to remove it
const MOVE_THRESHOLD = 6; // px — below this, a touch is a tap/long-press, not a drag
 
const clamp = (v, min, max) => Math.min(max, Math.max(min, v));
 
let nextDropId = 1;

const getChain = (dropId, cardsById) => {
  let leftMost = dropId;
  while (cardsById[leftMost].snapLeft != null){
    leftMost = cardsById[leftMost].snapLeft;
  }
  const chain = [];
  let cur = leftMost;
  while (cur != null) {
    chain.push(cur);
    cur = cardsById[cur].snapRight;
  }
  return chain;
}

const computeSnapTarget = (chainCards, otherCards) => {
  const leftCard = chainCards[0];
  const rightCard = chainCards[chainCards.length - 1];

  for (const other of otherCards) {
    // chain's right edge meeting this card's open left side
    if (other.snapLeft == null) {
      const dx = other.x - (rightCard.x + CARD_W);
      const dy = other.y - rightCard.y;
      if (Math.abs(dx) < SNAP_THRESHOLD && Math.abs(dy) < SNAP_THRESHOLD) {
        return { targetId: other.dropId, chainEdge: 'right' };
      }
    }
    // chain's left edge meeting this card's open right side
    if (other.snapRight == null) {
      const dx = (other.x + CARD_W) - leftCard.x;
      const dy = other.y - leftCard.y;
      if (Math.abs(dx) < SNAP_THRESHOLD && Math.abs(dy) < SNAP_THRESHOLD) {
        return { targetId: other.dropId, chainEdge: 'left' };
      }
    }
  }
  return null;
};


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
 
  const [selectedLevel, setSelectedLevel] = useState(LEVELS[0]);
  const [selectedUnit, setSelectedUnit] = useState(UNITS_BY_LEVEL[LEVELS[0]][0]);
  const [selectedLesson, setSelectedLesson] = useState('All');

  const [snapTarget, setSnapTarget] = useState(null);

  const [loggedIn, setLoggedIn] = useState(
    () => localStorage.getItem('wordBuilderLoggedIn') === 'true'
  );

  const handleLevelChange = (e) => {
    const level = e.target.value;
    setSelectedLevel(level);
    setSelectedUnit(UNITS_BY_LEVEL[level][0]);
  }

  const handleLogin = () => {
    localStorage.setItem('wordBuilderLoggedIn', 'true');
    setLoggedIn(true);
  }

  const handleLogout = () => {
    localStorage.removeItem('wordBuilderLoggedIn');
    setLoggedIn(false);
  }

  // ---------- coordinate + pan helpers ----------
  const screenToWorld = useCallback((clientX, clientY) => {
    const rect = viewportRef.current.getBoundingClientRect();
    return {
      x: (clientX - rect.left - pan.x) / zoom,
      y: (clientY - rect.top - pan.y) / zoom,
    };
  }, [pan, zoom]);
 
  const isOverBoard = (clientX, clientY) => {
    const rect = viewportRef.current.getBoundingClientRect();
    return clientX >= rect.left && clientX <= rect.right &&
           clientY >= rect.top && clientY <= rect.bottom;
  }

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
 
  const deleteMorphemes = () => {
    if (window.confirm('Remove all cards from the board?')) {
      setDropped([]);
    }
  }

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
 
      const cardsById = Object.fromEntries(dropped.map((c) => [c.dropId, c]));
      const chainIds = getChain(payload.dropId, cardsById);
      cardGesture.current.chainIds = chainIds;
      cardGesture.current.chainOffsets = Object.fromEntries(
        chainIds
          .filter((id) => id !== payload.dropId)
          .map((id) => [id, { dx: cardsById[id].x - payload.x, dy: cardsById[id].y - payload.y}])
      );

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

      if (isOverBoard(e.clientX, e.clientY)) {
        const world = screenToWorld(e.clientX, e.clientY);
        const ghostCard = { x: world.x - CARD_W / 2, y: world.y - CARD_H / 2 };
        setSnapTarget(computeSnapTarget([ghostCard], dropped));
      } else {
        setSnapTarget(null);
      }
      return;
    } 

    const world = screenToWorld(e.clientX, e.clientY);
    const x = world.x - g.grabDX;
    const y = world.y - g.grabDY;
    
    // move grabbed card, plus every chain member at stored offset
    const next = dropped.map((c) => {
      if (c.dropId === g.payload.dropId) return { ...c, x, y };
      const offset = g.chainOffsets[c.dropId];
      return offset ? { ...c, x: x + offset.dx, y: y + offset.dy } : c;
    });
    setDropped(next);

    // check whether either end of dragged chain is now near an open edge
    const chainSet = new Set(g.chainIds);
    const chainCards = next
      .filter((c) => chainSet.has(c.dropId))
      .sort((a, b) => a.x - b.x);
    const others = next.filter((c) => !chainSet.has(c.dropId));
    setSnapTarget(computeSnapTarget(chainCards, others));
  };
 
  const onCardPointerUp = (e) => {
    clearLongPress();
    const g = cardGesture.current;
    if (!g || g.pointerId !== e.pointerId) return;
    cardGesture.current = null;
 
    if (g.payload.source === 'tray') {

      if (g.moved && isOverBoard(e.clientX, e.clientY)) {
        const world = screenToWorld(e.clientX, e.clientY);
        const { page_front, page_back, row, front_col,
                  is_card, morpheme, unit_label, color, definition,
                  origin, note, index, front_has_icon, back_has_icon, icon_types,
                  level, unit, word_type, word_origin
                } = g.payload;
        
        let x = world.x - CARD_W / 2;
        let y = world.y - CARD_H / 2;
        let snapLeft = null;
        let snapRight = null; 
        const newId = nextDropId++;

        if (snapTarget) {
          const target = dropped.find((c) => c.dropId === snapTarget.targetId);
          y = target.y;
          if (snapTarget.chainEdge === 'right') {
            x = target.x - CARD_W;
            snapRight = target.dropId;
          } else {
            x = target.x + CARD_W;
            snapLeft = target.dropId;
          }
        }

        setDropped((prev) => {
          const withNewCard = [
            ...prev,
            { dropId: newId, morpheme, word_type, x, y, page_front, page_back,
          row, front_col, is_card, unit_label, color, definition, origin, note, index,
          front_has_icon, back_has_icon, icon_types, level, unit, word_origin,
          flipped: false, snapLeft, snapRight },
          ];
        if (!snapTarget) return withNewCard;

        // tell tgt card now connected with new card too
        return withNewCard.map((c) => 
          c.dropId === snapTarget.targetId  
            ? snapTarget.chainEdge === 'right'
            ? { ...c, snapLeft: newId }
            : { ...c, snapRight: newId}
            : c
          );
        });
      }

      // if (g.moved) {
      //   const world = screenToWorld(e.clientX, e.clientY);
      //   const rect = viewportRef.current.getBoundingClientRect();
      //   const overBoard =
      //     e.clientX >= rect.left && e.clientX <= rect.right &&
      //     e.clientY >= rect.top && e.clientY <= rect.bottom;
      //   if (overBoard) {
      //     const { page_front, page_back, row, front_col,
      //             is_card, morpheme, unit_label, color, definition,
      //             origin, note, index, front_has_icon, back_has_icon, icon_types,
      //             level, unit, word_type, word_origin
      //           } = g.payload;
      //     setDropped((prev) => [
      //       ...prev,
      //       { dropId: nextDropId++, morpheme, word_type, x: world.x - 45, y: world.y - 26, page_front, page_back, 
      //         row, front_col, is_card, unit_label, color, definition, origin, note, index, front_has_icon, back_has_icon, icon_types,
      //         level, unit, word_origin, flipped: false, snapLeft: null, snapRight: null
      //        },
      //     ]);
      //   }
      // }
      setGhost(null);
    } else if (snapTarget) {
      applySnap(g.payload.dropId, snapTarget);
    }
    setSnapTarget(null);
  };
 
  const removeCard = (dropId) => {
    setDropped((prev) => {
      const removed = prev.find((c) => c.dropId === dropId);
      return prev
        .filter((c) => c.dropId !== dropId)
        .map((c) => {
          if (removed?.snapLeft === c.dropId) return { ...c, snapRight: null };
          if (removed?.snapRight === c.dropId) return { ...c, snapLeft: null };
          return c;
        });
    });
  };

  const toggleFlip = (dropId) => {
    setDropped((prev) => {
      const cardsById = Object.fromEntries(prev.map((c) => [c.dropId, c]));
      const chainIds = new Set(getChain(dropId, cardsById));
      const newFlipped = !cardsById[dropId].flipped;
      return prev.map((c) => (chainIds.has(c.dropId) ? { ...c, flipped: newFlipped } : c));
    });
  };

  const applySnap = (draggedId, snap) => {
    setDropped((prev) => {
      const cardsById = Object.fromEntries(prev.map((c) => [c.dropId, c]));
      const chainIds = getChain(draggedId, cardsById)
        .map((id) => cardsById[id])
        .sort((a, b) => a.x - b.x)
        .map((c) => c.dropId);

      const target = cardsById[snap.targetId];
      const edgeCardId = snap.chainEdge === 'right' ? chainIds[chainIds.length - 1] : chainIds[0];
      const edgeCard = cardsById[edgeCardId];

      // nudge the whole chain so the connecting edge sits flush, not just "close enough"
      const dx = snap.chainEdge === 'right'
        ? (target.x - CARD_W) - edgeCard.x
        : (target.x + CARD_W) - edgeCard.x;
      const dy = target.y - edgeCard.y;

      return prev.map((c) => {
        if (chainIds.includes(c.dropId)) {
          const moved = { ...c, x: c.x + dx, y: c.y + dy };
          if (c.dropId === edgeCardId) {
            return snap.chainEdge === 'right'
              ? { ...moved, snapRight: snap.targetId }
              : { ...moved, snapLeft: snap.targetId };
          }
          return moved;
        }
        if (c.dropId === snap.targetId) {
          return snap.chainEdge === 'right'
            ? { ...c, snapLeft: edgeCardId }
            : { ...c, snapRight: edgeCardId };
        }
        return c;
      });
    });
  };

  return (
        <div className="app">
      {/* LEFT — static panel */}
      <aside className="sidebar">
        <header className="header">
          <div className="header-text">
            <h1 className="title">Word Builder</h1>
            <p className="subtitle">Drag pieces onto the board</p>
          </div>
          {loggedIn && (
            <button className='logout-btn' onClick={handleLogout}>Logout</button>
          )}
        </header>
 
        {loggedIn ? (
          <>
           <div className="filters">
          <label className="filter-label">
            Level
            <select value={selectedLevel} onChange={handleLevelChange}>
              {LEVELS.map((level) => (
                <option key={level} value={level}>{level}</option>
              ))}
            </select>
          </label>

          <label className="filter-label">
            Unit
            <select value={selectedUnit} onChange={(e) => setSelectedUnit(e.target.value)}>
              {UNITS_BY_LEVEL[selectedLevel].map((unit) => (
                <option key={unit} value={unit}>{unit}</option>
              ))}
            </select>
          </label>

          <label className="filter-label">
            Lesson
            <select value={selectedLesson} onChange={(e) => setSelectedLesson(e.target.value)}>
              {LESSONS.map((lesson) => (
                <option key={lesson} value={lesson}>{lesson}</option>
              ))}
            </select>
          </label>
        </div>

        <div className="legend">
          <div className="legend-row">
            <div className="legend-item">
              <span className="legend-swatch" style={{ background: ORIGIN_COLOR['Greek'] }} />
              Greek
            </div>
            <div className="legend-item">
              <span className="legend-swatch" style={{ background: ORIGIN_COLOR['Latin'] }} />
              Latin
            </div>
            <div className="legend-item">
              <span className="legend-swatch" style={{ background: ORIGIN_COLOR['Anglo-Saxon'] }} />
              Anglo-Saxon
            </div>
          </div>

          <div className="legend-row">
            <div className="legend-item">
              <span className="legend-emoji">👪</span>
              Alternate form
            </div>
            <div className="legend-item">
              <span className="legend-emoji">🦎</span>
              Chameleon prefix
            </div>
          </div>
        </div>

        <div className="tray-scroll">
          {WORD_TYPES.map((group) => (
            <div key={group} className="tray-group">
              <p className="group-label" style={{ color: TYPE_COLOR[group] }}>
                {group === 'prefix' ? 'Prefixes' : group === 'root' ? 'Root Words' : group === 'base' ? 'Base Words' : 'Suffixes'}
              </p>
              <div className="tray-grid">
                {MORPHEMES.filter((m) => m.word_type === group &&
                                         m.level === selectedLevel && 
                                         m.unit === selectedUnit &&
                                         getLessons(m).includes(selectedLesson)
                                  ).map((m) => (
                  <div
                    key={m.index}
                    data-card
                    className="card"
                    onPointerDown={(e) => beginCardPointer(e, { source: 'tray', ...m })}
                    onPointerMove={onCardPointerMove}
                    onPointerUp={onCardPointerUp}
                    style={{ borderColor: TYPE_COLOR[m.word_type], color: ORIGIN_COLOR[m.word_origin]}} // TODO: update here
                  >
                    {m.morpheme}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
        </>
        ) : (
          <LoginForm onLogin={handleLogin} />
        )}

       
      </aside>
 
      {/* RIGHT — the board */}
      <main className="board">
        <div className="zoom-bar">
          <button className="zoom-btn" onClick={() => zoomAtCenter(1 / 1.2)}>−</button>
          <span className="zoom-label">{Math.round(zoom * 100)}%</span>
          <button className="zoom-btn" onClick={() => zoomAtCenter(1.2)}>+</button>
          <button className="reset-btn" onClick={resetView}>Reset Grid Position</button>
          <button className='delete-btn' onClick={deleteMorphemes}>Delete All Cards</button>
          <span className="hint">Double click a card to remove it</span>
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
                className={`placed-card ${snapTarget?.targetId === card.dropId ? 'snap-target' : ''}`}
                onPointerDown={(e) => beginCardPointer(e, { source: 'canvas', ...card })}
                onPointerMove={onCardPointerMove}
                onPointerUp={onCardPointerUp}
                onDoubleClick={() => removeCard(card.dropId)}
                style={{
                  left: card.x,
                  top: card.y,
                  borderColor: TYPE_COLOR[card.word_type],
                }}
                //title="Double-click (or hold on touch-screen) to remove"
              >
                <button
                  className="flip-btn"
                  onPointerDown={(e) => e.stopPropagation()}
                  onClick={(e) => { e.stopPropagation(); toggleFlip(card.dropId); }}
                  onDoubleClick={(e) => e.stopPropagation()}
                >
                  ↻
                </button>

                {!card.flipped ? (
                  <div className="card-face card-face-front" style={{ color: ORIGIN_COLOR[card.word_origin] }}>
                    <span className="placed-word">{card.morpheme}</span>
                    <span className="placed-meta">{card.unit_label}</span>
                    {card.front_has_icon && (
                      <span className="placed-icon placed-icon-right">
                        {card.icon_types.includes('alternate') ? '👪' : ''}
                        {card.icon_types.includes('chameleon') ? '🦎' : ''}
                      </span>
                    )}
                  </div>
                ) : (
                  <div className="card-face card-face-back">
                    <span className="back-morpheme">{card.morpheme}</span>
                    <span className="back-definition">{card.definition}</span>

                    <div className={`back-footer ${card.back_has_icon ? 'has-icon' : ''}`}>
                      <span className="back-origin">{card.origin}</span>
                      {card.note && <span className="back-note">{card.note}</span>}
                    </div>

                    {card.back_has_icon && (
                      <span className="placed-icon placed-icon-left">
                        {card.icon_types.includes('alternate') ? '👪' : ''}
                        {card.icon_types.includes('chameleon') ? '🦎' : ''}
                      </span>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </main>
 
      {/* floating preview while dragging a new card in from the tray */}
      {ghost && (
        <div
          className="ghost"
          style={{ left: ghost.clientX, top: ghost.clientY, borderColor: TYPE_COLOR[ghost.word_type],color: ORIGIN_COLOR[ghost.word_origin], width: CARD_W, height: CARD_H }}
        >
          {ghost.morpheme}
        </div>
      )}
    </div>

  )
}

export default App
