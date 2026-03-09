/**
 * Client-side full-text search across portal pages
 */

(function () {
  'use strict';

  let searchIndex = [];

  /**
   * Build search index from DOM elements with data-searchable attribute
   */
  function buildSearchIndex() {
    searchIndex = [];
    const items = document.querySelectorAll('[data-searchable]');
    items.forEach(function (el) {
      const text = (el.dataset.name || '') + ' ' +
                   (el.dataset.projects || '') + ' ' +
                   (el.dataset.tech || '') + ' ' +
                   (el.dataset.category || '') + ' ' +
                   (el.dataset.status || '') + ' ' +
                   (el.textContent || '');
      searchIndex.push({
        element: el,
        text: text.toLowerCase(),
      });
    });
  }

  /**
   * Handle search input
   */
  window.handleSearch = function (query) {
    if (searchIndex.length === 0) buildSearchIndex();

    const q = (query || '').toLowerCase().trim();
    let shown = 0;

    searchIndex.forEach(function (item) {
      if (!q || item.text.includes(q)) {
        item.element.style.display = '';
        shown++;
      } else {
        item.element.style.display = 'none';
      }
    });

    // Update result count
    const counter = document.getElementById('search-result-count');
    if (counter) {
      counter.textContent = q ? `${shown} result${shown !== 1 ? 's' : ''}` : '';
    }
  };

  /**
   * Handle filter button click
   */
  window.handleFilter = function (btn, filterValue) {
    // Toggle active state
    if (btn.classList.contains('active')) {
      btn.classList.remove('active');
      handleSearch('');
      return;
    }

    // Deactivate other buttons
    const siblings = btn.parentElement.querySelectorAll('.filter-btn');
    siblings.forEach(function (b) { b.classList.remove('active'); });
    btn.classList.add('active');

    handleSearch(filterValue);
  };

  // Global search from sidebar
  function initGlobalSearch() {
    const input = document.getElementById('global-search');
    if (!input) return;

    input.addEventListener('input', function () {
      handleSearch(this.value);
    });

    input.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') {
        this.value = '';
        handleSearch('');
      }
    });
  }

  // Page-level search input
  function initPageSearch() {
    const input = document.getElementById('page-search');
    if (!input) return;

    input.addEventListener('input', function () {
      handleSearch(this.value);
    });
  }

  // Init
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
      buildSearchIndex();
      initGlobalSearch();
      initPageSearch();
    });
  } else {
    buildSearchIndex();
    initGlobalSearch();
    initPageSearch();
  }
})();
