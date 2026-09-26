/**
 * Live Activity Event Stream Renderer.
 */
const ActivityUI = {
  render(events = []) {
    const feed = document.getElementById('activity-full-feed');
    if (!feed) return;

    if (!events || events.length === 0) {
      feed.innerHTML = `<div style="text-align:center;padding:24px;color:var(--text-muted)">No activity events recorded yet.</div>`;
      return;
    }

    feed.innerHTML = events
      .map(
        (ev) => `
        <div class="activity-item ${ev.severity}">
          <span class="activity-time">${AppUtils.formatTime(ev.created_at)}</span>
          <span class="badge ${AppUtils.badgeClass(ev.severity)}">${ev.event_type}</span>
          <div>
            <span>${AppUtils.escapeHtml(ev.message)}</span>
            ${ev.node_id ? `<span class="mono-code" style="margin-left:8px">${ev.node_id.toUpperCase()}</span>` : ''}
          </div>
        </div>
      `
      )
      .join('');
  },
};

window.ActivityUI = ActivityUI;
