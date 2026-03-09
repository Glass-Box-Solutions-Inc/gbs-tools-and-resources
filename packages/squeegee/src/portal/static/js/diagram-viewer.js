/**
 * Diagram Viewer — Click-to-zoom, pan, fullscreen modal for Mermaid diagrams
 *
 * Features:
 * - Click diagram to open fullscreen modal
 * - Mouse wheel / pinch zoom
 * - Click-drag panning
 * - Keyboard: Escape to close, +/- to zoom, 0 to reset
 */

(function () {
  'use strict';

  let currentScale = 1;
  let currentX = 0;
  let currentY = 0;
  let isDragging = false;
  let dragStartX = 0;
  let dragStartY = 0;

  const MIN_SCALE = 0.25;
  const MAX_SCALE = 5;
  const ZOOM_STEP = 0.15;

  /**
   * Open the diagram modal with content from a diagram container
   */
  window.openDiagramModal = function (element) {
    const modal = document.getElementById('diagram-modal');
    const content = document.getElementById('diagram-modal-content');
    if (!modal || !content) return;

    // Clone the SVG or mermaid content
    const svg = element.querySelector('svg');
    const mermaidDiv = element.querySelector('.mermaid');

    if (svg) {
      const clone = svg.cloneNode(true);
      clone.style.width = 'auto';
      clone.style.height = 'auto';
      clone.style.maxWidth = 'none';
      clone.style.maxHeight = 'none';
      clone.removeAttribute('width');
      clone.removeAttribute('height');
      content.innerHTML = '';
      content.appendChild(clone);
    } else if (mermaidDiv) {
      content.innerHTML = mermaidDiv.innerHTML;
    } else {
      content.innerHTML = element.innerHTML;
    }

    // Reset transform
    currentScale = 1;
    currentX = 0;
    currentY = 0;
    applyTransform(content);

    // Show modal
    modal.classList.remove('hidden');
    modal.classList.add('flex');
    document.body.style.overflow = 'hidden';
  };

  /**
   * Close the diagram modal
   */
  window.closeDiagramModal = function () {
    const modal = document.getElementById('diagram-modal');
    if (!modal) return;
    modal.classList.add('hidden');
    modal.classList.remove('flex');
    document.body.style.overflow = '';
  };

  /**
   * Apply CSS transform for zoom/pan
   */
  function applyTransform(el) {
    const inner = el.firstElementChild;
    if (inner) {
      inner.style.transform = `translate(${currentX}px, ${currentY}px) scale(${currentScale})`;
      inner.style.transformOrigin = 'center center';
    }
  }

  // Keyboard handlers
  document.addEventListener('keydown', function (e) {
    const modal = document.getElementById('diagram-modal');
    if (!modal || modal.classList.contains('hidden')) return;

    if (e.key === 'Escape') {
      closeDiagramModal();
    } else if (e.key === '+' || e.key === '=') {
      currentScale = Math.min(MAX_SCALE, currentScale + ZOOM_STEP);
      applyTransform(document.getElementById('diagram-modal-content'));
    } else if (e.key === '-') {
      currentScale = Math.max(MIN_SCALE, currentScale - ZOOM_STEP);
      applyTransform(document.getElementById('diagram-modal-content'));
    } else if (e.key === '0') {
      currentScale = 1;
      currentX = 0;
      currentY = 0;
      applyTransform(document.getElementById('diagram-modal-content'));
    }
  });

  // Mouse wheel zoom
  document.addEventListener('wheel', function (e) {
    const modal = document.getElementById('diagram-modal');
    if (!modal || modal.classList.contains('hidden')) return;

    e.preventDefault();
    const delta = e.deltaY > 0 ? -ZOOM_STEP : ZOOM_STEP;
    currentScale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, currentScale + delta));
    applyTransform(document.getElementById('diagram-modal-content'));
  }, { passive: false });

  // Mouse drag panning
  document.addEventListener('mousedown', function (e) {
    const modal = document.getElementById('diagram-modal');
    if (!modal || modal.classList.contains('hidden')) return;
    const content = document.getElementById('diagram-modal-content');
    if (!content || !content.contains(e.target)) return;

    isDragging = true;
    dragStartX = e.clientX - currentX;
    dragStartY = e.clientY - currentY;
  });

  document.addEventListener('mousemove', function (e) {
    if (!isDragging) return;
    currentX = e.clientX - dragStartX;
    currentY = e.clientY - dragStartY;
    applyTransform(document.getElementById('diagram-modal-content'));
  });

  document.addEventListener('mouseup', function () {
    isDragging = false;
  });

  /**
   * Initialize mermaid diagrams on the page (lazy)
   */
  window.initMermaidDiagrams = async function () {
    const diagrams = document.querySelectorAll('.mermaid:not([data-processed])');
    for (const el of diagrams) {
      try {
        el.setAttribute('data-processed', 'true');
        const code = el.textContent.trim();
        if (!code) continue;
        const id = 'mermaid-' + Math.random().toString(36).slice(2, 10);
        const { svg } = await mermaid.render(id, code);
        el.innerHTML = svg;
      } catch (err) {
        console.warn('Mermaid render failed:', err.message);
        el.innerHTML = '<div class="text-red-400 text-sm p-4">Diagram render failed</div>';
      }
    }
  };

  // Auto-init visible mermaid diagrams on page load
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
      window.initMermaidDiagrams();
    });
  } else {
    window.initMermaidDiagrams();
  }
})();
