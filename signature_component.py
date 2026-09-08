from __future__ import annotations

import base64
import binascii
from io import BytesIO

import numpy as np
import streamlit as st
from PIL import Image, UnidentifiedImageError

from utils import signature_from_canvas, validate_signature_png

SIGNATURE_HTML = """
<div class="signature-wrap">
  <div class="signature-hint">Desenhe sua assinatura dentro da área branca</div>
  <canvas class="signature-canvas" aria-label="Área para desenhar a assinatura"></canvas>
  <div class="signature-actions">
    <button type="button" class="expand">⛶ Ampliar tela</button>
    <button type="button" class="undo">↶ Desfazer</button>
    <button type="button" class="clear">Limpar</button>
    <button type="button" class="finish">Concluir assinatura</button>
  </div>
</div>
"""

SIGNATURE_CSS = """
.signature-wrap {
  width: 100%; box-sizing: border-box; font-family: var(--st-font);
  color: var(--st-text-color); background: var(--st-background-color);
}
.signature-hint { font-size: 14px; color: #667085; margin-bottom: 7px; }
.signature-canvas {
  display: block; width: 100%; height: clamp(165px, 25vw, 220px);
  box-sizing: border-box; background: #fff; border: 2px solid #98a2b3;
  border-radius: 10px; touch-action: none; cursor: crosshair;
}
.signature-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
.signature-actions button {
  min-height: 46px; padding: 9px 14px; border-radius: 9px;
  border: 1px solid #98a2b3; background: #fff; color: #172033;
  font: 600 15px var(--st-font); cursor: pointer;
}
.signature-actions .finish {
  flex: 1 1 190px; background: #b5122b; border-color: #b5122b; color: white;
}
.signature-wrap.expanded {
  position: fixed; inset: 0; z-index: 2147483000; padding: 14px;
  background: #f5f7fa; display: flex; flex-direction: column;
}
.signature-wrap.expanded .signature-canvas {
  flex: 1 1 auto; width: 100%; height: auto; min-height: 0;
}
.signature-wrap.expanded .signature-actions { flex: 0 0 auto; }
.signature-wrap.expanded .expand { background: #172033; color: white; }
@media (max-width: 640px) {
  .signature-hint { font-size: 16px; }
  .signature-actions { display: grid; grid-template-columns: 1fr 1fr; }
  .signature-actions button { width: 100%; font-size: 16px; }
  .signature-actions .finish { grid-column: 1 / -1; }
}
"""

SIGNATURE_JS = """
export default function({ parentElement, data, setStateValue }) {
  const wrap = parentElement.querySelector('.signature-wrap');
  const canvas = parentElement.querySelector('.signature-canvas');
  const context = canvas.getContext('2d');
  const expandButton = parentElement.querySelector('.expand');
  const undoButton = parentElement.querySelector('.undo');
  const clearButton = parentElement.querySelector('.clear');
  const finishButton = parentElement.querySelector('.finish');
  let drawing = false;
  let moved = false;
  let points = [];
  let history = [];
  let resizeTimer;

  function restoreImage(value) {
    if (!value) return;
    const image = new Image();
    image.onload = () => {
      const rect = canvas.getBoundingClientRect();
      context.drawImage(image, 0, 0, rect.width, rect.height);
    };
    image.src = value;
  }

  function resizeCanvas(source) {
    const rect = canvas.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const ratio = Math.max(window.devicePixelRatio || 1, 1);
    canvas.width = Math.round(rect.width * ratio);
    canvas.height = Math.round(rect.height * ratio);
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    context.lineCap = 'round';
    context.lineJoin = 'round';
    context.strokeStyle = '#172033';
    context.lineWidth = 3.5;
    restoreImage(source);
  }

  function snapshot() {
    return canvas.toDataURL('image/png');
  }

  function coordinates(event) {
    const rect = canvas.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  }

  canvas.onpointerdown = (event) => {
    event.preventDefault();
    history.push(snapshot());
    if (history.length > 20) history.shift();
    drawing = true;
    moved = false;
    points = [coordinates(event)];
    canvas.setPointerCapture(event.pointerId);
  };

  canvas.onpointermove = (event) => {
    if (!drawing) return;
    event.preventDefault();
    const point = coordinates(event);
    const previous = points[points.length - 1];
    const midpoint = { x: (previous.x + point.x) / 2, y: (previous.y + point.y) / 2 };
    context.beginPath();
    context.moveTo(previous.x, previous.y);
    context.quadraticCurveTo(previous.x, previous.y, midpoint.x, midpoint.y);
    context.stroke();
    points.push(point);
    moved = true;
  };

  function stopDrawing(event) {
    if (!drawing) return;
    event.preventDefault();
    if (!moved && points.length) {
      const point = points[0];
      context.beginPath();
      context.arc(point.x, point.y, 1.8, 0, Math.PI * 2);
      context.fillStyle = '#172033';
      context.fill();
    }
    drawing = false;
  }
  canvas.onpointerup = stopDrawing;
  canvas.onpointercancel = stopDrawing;

  undoButton.onclick = () => {
    const previous = history.pop();
    if (!previous) return;
    context.clearRect(0, 0, canvas.width, canvas.height);
    restoreImage(previous);
  };

  clearButton.onclick = () => {
    history = [];
    context.clearRect(0, 0, canvas.width, canvas.height);
    setStateValue('image_data', '');
  };

  finishButton.onclick = () => {
    const value = snapshot();
    wrap.classList.remove('expanded');
    document.body.style.overflow = '';
    setStateValue('image_data', value);
  };

  expandButton.onclick = () => {
    const source = snapshot();
    const expanded = wrap.classList.toggle('expanded');
    expandButton.textContent = expanded ? '✕ Fechar tela grande' : '⛶ Ampliar tela';
    document.body.style.overflow = expanded ? 'hidden' : '';
    requestAnimationFrame(() => resizeCanvas(source));
  };

  const observer = new ResizeObserver(() => {
    clearTimeout(resizeTimer);
    const source = canvas.width ? snapshot() : (data?.value || '');
    resizeTimer = setTimeout(() => resizeCanvas(source), 80);
  });
  resizeCanvas(data?.value || '');
  observer.observe(canvas);

  return () => {
    observer.disconnect();
    clearTimeout(resizeTimer);
    document.body.style.overflow = '';
  };
}
"""

_signature_pad = st.components.v2.component(
    "responsive_signature_pad",
    html=SIGNATURE_HTML,
    css=SIGNATURE_CSS,
    js=SIGNATURE_JS,
)


def signature_pad(*, key: str) -> bytes | None:
    component_state = st.session_state.get(key, {})
    if hasattr(component_state, "get"):
        current_value = component_state.get("image_data", "")
    else:
        current_value = ""
    result = _signature_pad(
        data={"value": current_value or ""},
        default={"image_data": current_value or ""},
        on_image_data_change=lambda: None,
        key=key,
    )
    value = result.image_data
    if not value or not str(value).startswith("data:image/png;base64,"):
        return None
    try:
        image_bytes = base64.b64decode(str(value).split(",", 1)[1], validate=True)
        if len(image_bytes) > 5_000_000:
            return None
        with Image.open(BytesIO(image_bytes)) as image:
            if image.width > 5000 or image.height > 5000:
                return None
            pixels = np.asarray(image.convert("RGBA"))
        signature = signature_from_canvas(pixels)
        if signature:
            with Image.open(BytesIO(signature)) as image:
                if image.width > 1800 or image.height > 900:
                    image.thumbnail((1800, 900), Image.Resampling.LANCZOS)
                    output = BytesIO()
                    image.save(output, format="PNG", optimize=True)
                    signature = output.getvalue()
        return validate_signature_png(signature) if signature else None
    except (
        binascii.Error,
        Image.DecompressionBombError,
        UnidentifiedImageError,
        OSError,
        ValueError,
    ):
        return None
