/**
 * Sidebar Navigation — collapse/expand sections, mobile toggle
 */

(function () {
  'use strict';

  /**
   * Toggle mobile sidebar
   */
  window.toggleSidebar = function () {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebar-overlay');
    if (!sidebar) return;

    const isOpen = !sidebar.classList.contains('-translate-x-full');
    if (isOpen) {
      sidebar.classList.add('-translate-x-full');
      overlay?.classList.add('hidden');
    } else {
      sidebar.classList.remove('-translate-x-full');
      overlay?.classList.remove('hidden');
    }
  };

  /**
   * Initialize nav section toggles
   */
  function initNavSections() {
    const toggles = document.querySelectorAll('.nav-section-toggle');
    toggles.forEach(function (toggle) {
      toggle.addEventListener('click', function () {
        const items = this.nextElementSibling;
        if (!items) return;

        const icon = this.querySelector('svg');
        if (items.classList.contains('collapsed')) {
          items.classList.remove('collapsed');
          items.style.maxHeight = items.scrollHeight + 'px';
          if (icon) icon.style.transform = '';
        } else {
          items.classList.add('collapsed');
          items.style.maxHeight = '0';
          if (icon) icon.style.transform = 'rotate(-90deg)';
        }
      });

      // Set initial max-height for animation
      const items = toggle.nextElementSibling;
      if (items && !items.classList.contains('collapsed')) {
        items.style.maxHeight = items.scrollHeight + 'px';
      }
    });
  }

  // Close sidebar on outside click (mobile)
  document.addEventListener('click', function (e) {
    const sidebar = document.getElementById('sidebar');
    const menuBtn = document.getElementById('mobile-menu-btn');
    if (!sidebar || !menuBtn) return;

    if (window.innerWidth < 1024 &&
        !sidebar.contains(e.target) &&
        !menuBtn.contains(e.target) &&
        !sidebar.classList.contains('-translate-x-full')) {
      toggleSidebar();
    }
  });

  // Init on load
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initNavSections);
  } else {
    initNavSections();
  }
})();
