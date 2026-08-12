(function () {
  const slug = window.location.pathname.split("/").pop();
  const form = document.getElementById("gig-form");
  const container = document.getElementById("setlist-container");
  const generateBtn = document.getElementById("generate-btn");
  const refreshBtn = document.getElementById("refresh-btn");
  const exportActions = document.getElementById("export-actions");
  const exportTxt = document.getElementById("export-txt");
  const exportCsv = document.getElementById("export-csv");

  let currentSeed = null;

  function formData() {
    const fd = new FormData(form);
    const params = new URLSearchParams();
    for (const [key, value] of fd.entries()) {
      params.append(key, value);
    }
    return params;
  }

  function selectedColumns() {
    return Array.from(
      form.querySelectorAll('input[name="export_columns"]:checked')
    ).map((el) => el.value);
  }

  function updateExportLinks() {
    const params = formData();
    const txtParams = new URLSearchParams(params);
    const csvParams = new URLSearchParams(params);
    selectedColumns().forEach((col) => csvParams.append("columns", col));
    if (currentSeed !== null) {
      txtParams.set("seed", currentSeed);
      csvParams.set("seed", currentSeed);
    }
    exportTxt.href = `/bands/${slug}/export.txt?${txtParams}`;
    exportCsv.href = `/bands/${slug}/export.csv?${csvParams}`;
    exportActions.classList.remove("hidden");
  }

  async function generate() {
    const response = await fetch(`/bands/${slug}/generate`, {
      method: "POST",
      body: formData(),
    });
    const html = await response.text();
    container.innerHTML = html;
    const preview = container.querySelector(".setlist-preview");
    currentSeed = preview?.dataset.seed || null;
    refreshBtn.disabled = false;
    updateExportLinks();
    initDragDrop();
  }

  async function reorder() {
    const items = container.querySelectorAll(".song-item");
    const orderData = Array.from(items).map((item) => ({
      title: item.dataset.title,
      set: parseInt(item.dataset.set, 10),
    }));

    const fd = new FormData();
    fd.append("duration_minutes", form.duration_minutes.value);
    fd.append("order_data", JSON.stringify(orderData));

    const response = await fetch(`/bands/${slug}/reorder`, {
      method: "POST",
      body: fd,
    });
    const html = await response.text();
    container.innerHTML = html;
    initDragDrop();
  }

  function initDragDrop() {
    const lists = container.querySelectorAll(".song-list");
    let dragged = null;

    container.querySelectorAll(".song-item").forEach((item) => {
      item.addEventListener("dragstart", (e) => {
        dragged = item;
        item.classList.add("dragging");
        e.dataTransfer.effectAllowed = "move";
      });

      item.addEventListener("dragend", () => {
        item.classList.remove("dragging");
        dragged = null;
        lists.forEach((list) => list.parentElement.classList.remove("drag-over"));
        reorder();
      });
    });

    lists.forEach((list) => {
      list.addEventListener("dragover", (e) => {
        e.preventDefault();
        list.parentElement.classList.add("drag-over");
        const after = getDragAfterElement(list, e.clientY);
        if (dragged) {
          if (after) {
            list.insertBefore(dragged, after);
          } else {
            list.appendChild(dragged);
          }
          dragged.dataset.set = list.dataset.set;
        }
      });

      list.addEventListener("dragleave", () => {
        list.parentElement.classList.remove("drag-over");
      });
    });
  }

  function getDragAfterElement(list, y) {
    const items = [...list.querySelectorAll(".song-item:not(.dragging)")];
    return items.reduce(
      (closest, child) => {
        const box = child.getBoundingClientRect();
        const offset = y - box.top - box.height / 2;
        if (offset < 0 && offset > closest.offset) {
          return { offset, element: child };
        }
        return closest;
      },
      { offset: Number.NEGATIVE_INFINITY, element: null }
    ).element;
  }

  generateBtn.addEventListener("click", generate);
  refreshBtn.addEventListener("click", generate);
})();
