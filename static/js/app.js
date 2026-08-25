function renderLineChart(canvasId, labels, values, label, color) {
  const canvas = document.getElementById(canvasId);
  if (!canvas || !labels.length) return;

  new Chart(canvas, {
    type: "line",
    data: {
      labels,
      datasets: [{
        label,
        data: values,
        borderColor: color,
        backgroundColor: `${color}22`,
        fill: true,
        tension: 0.35,
      }],
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: { y: { beginAtZero: true } },
    },
  });
}

document.addEventListener("DOMContentLoaded", () => {
  if (window.UREMBO_CHARTS) {
    const commission = window.UREMBO_CHARTS.commission || [];
    const utilization = window.UREMBO_CHARTS.utilization || [];

    renderLineChart(
      "commissionChart",
      commission.map((item) => item.date || "N/A"),
      commission.map((item) => item.commission || 0),
      "Commission",
      "#e40000"
    );

    renderLineChart(
      "utilizationChart",
      utilization.map((item) => item.date || "N/A"),
      utilization.map((item) => item.rate || 0),
      "Utilization %",
      "#b30000"
    );
  }

  const syncBtn = document.getElementById("sync-btn");
  if (syncBtn) {
    syncBtn.addEventListener("click", async () => {
      syncBtn.disabled = true;
      syncBtn.textContent = "Syncing...";
      try {
        const response = await fetch("/api/sync", { method: "POST" });
        const data = await response.json();
        if (data.error) {
          alert(data.error);
        } else {
          window.location.reload();
        }
      } catch (error) {
        alert("Sync failed. Please try again.");
      } finally {
        syncBtn.disabled = false;
        syncBtn.textContent = "Sync Now";
      }
    });
  }
});
