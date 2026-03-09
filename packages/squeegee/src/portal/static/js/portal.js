/**
 * Portal Core JS — Tab switching, heatmap drill-down, accordion, utilities
 */

(function () {
  'use strict';

  /**
   * Switch tabs within a container
   * @param {HTMLElement} button - Clicked tab button
   * @param {string} tabId - Target tab content ID
   */
  window.switchTab = function (button, tabId) {
    // Find parent tab container
    const container = button.closest('.tab-container') || button.parentElement.parentElement;

    // Deactivate all tab buttons in this group
    const tabBar = button.parentElement;
    tabBar.querySelectorAll('.tab-btn').forEach(function (btn) {
      btn.classList.remove('active');
    });
    button.classList.add('active');

    // Hide all tab content in this container
    container.querySelectorAll('.tab-content').forEach(function (content) {
      content.classList.remove('active');
    });

    // Show target tab
    const target = document.getElementById(tabId);
    if (target) target.classList.add('active');
  };

  /**
   * Toggle accordion section
   */
  window.toggleAccordion = function (header) {
    const body = header.nextElementSibling;
    if (!body) return;

    const isOpen = body.classList.contains('open');

    if (isOpen) {
      body.classList.remove('open');
      header.classList.remove('open');
    } else {
      body.classList.add('open');
      header.classList.add('open');

      // Lazy-init mermaid diagrams in this section
      if (window.initMermaidDiagrams) {
        setTimeout(function () { window.initMermaidDiagrams(); }, 100);
      }
    }
  };

  /**
   * Open commit detail panel (heatmap drill-down)
   */
  window.openCommitPanel = function (developer, project) {
    const drawer = document.getElementById('commit-drawer');
    const backdrop = document.getElementById('commit-drawer-backdrop');
    const title = document.getElementById('commit-drawer-title');
    const content = document.getElementById('commit-drawer-content');
    if (!drawer || !content) return;

    // Get commits from embedded data
    var commitsByCell = window.COMMITS_BY_CELL || {};
    var key = developer + '::' + project;
    var commits = commitsByCell[key] || [];

    title.textContent = developer + ' in ' + project;

    if (commits.length === 0) {
      content.innerHTML = '<p class="text-gray-500 text-sm">No commits found.</p>';
    } else {
      // Sort by timestamp descending
      commits.sort(function (a, b) {
        return new Date(b.timestamp) - new Date(a.timestamp);
      });

      var html = '<div class="space-y-3">';
      commits.forEach(function (commit) {
        var dateStr = formatCommitDate(commit.timestamp);
        var shaDisplay = commit.sha || '';
        html += '<div class="p-3 rounded-lg bg-gray-800/50 border border-gray-700/50">';
        html += '<div class="flex items-center gap-2 mb-1">';
        html += '<code class="text-xs text-cyan-400 font-mono">' + escHtml(shaDisplay) + '</code>';
        html += '<span class="text-xs text-gray-500">' + escHtml(dateStr) + '</span>';
        html += '</div>';
        html += '<p class="text-sm text-gray-300">' + escHtml(commit.message || '') + '</p>';
        if (commit.url) {
          html += '<a href="' + escHtml(commit.url) + '" target="_blank" class="text-xs text-blue-400 hover:underline mt-1 inline-block">View on GitHub</a>';
        }
        html += '</div>';
      });
      html += '</div>';
      content.innerHTML = html;
    }

    // Show drawer
    drawer.classList.remove('translate-x-full');
    backdrop.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
  };

  /**
   * Close commit detail panel
   */
  window.closeCommitPanel = function () {
    var drawer = document.getElementById('commit-drawer');
    var backdrop = document.getElementById('commit-drawer-backdrop');
    if (drawer) drawer.classList.add('translate-x-full');
    if (backdrop) backdrop.classList.add('hidden');
    document.body.style.overflow = '';
  };

  /**
   * Escape HTML for safe insertion
   */
  function escHtml(str) {
    if (!str) return '';
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }
  window.escHtml = escHtml;

  /**
   * Format commit date for display
   */
  function formatCommitDate(isoStr) {
    if (!isoStr) return '';
    var d = new Date(isoStr);
    if (isNaN(d.getTime())) return isoStr;
    var months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    return months[d.getMonth()] + ' ' + d.getDate() + ', ' + d.getFullYear() + ' ' +
           d.getHours().toString().padStart(2, '0') + ':' + d.getMinutes().toString().padStart(2, '0');
  }

  // Close drawer on Escape
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      closeCommitPanel();
    }
  });

  // Init responsive table wrapping
  function initResponsiveTables() {
    var tables = document.querySelectorAll('table');
    tables.forEach(function (table) {
      if (table.closest('.table-responsive')) return;
      if (table.scrollWidth > table.clientWidth) {
        var wrapper = document.createElement('div');
        wrapper.className = 'table-responsive';
        table.parentNode.insertBefore(wrapper, table);
        wrapper.appendChild(table);
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initResponsiveTables);
  } else {
    initResponsiveTables();
  }
})();
