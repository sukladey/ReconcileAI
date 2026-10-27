
"use strict";

const $ = id => document.getElementById(id);

let results = [];

const PIE_COLORS = [
  "#f97316",
  "#e11d48",
  "#8b5cf6",
  "#d97706",
  "#dc2626",
  "#0284c7",
  "#64748b"
];

/* ---------------- CSV PARSING ---------------- */

function parseCSV(text) {
  text = text.replace(/^\uFEFF/, "");

  const rows = [];
  let row = [];
  let field = "";
  let quoted = false;

  for (let i = 0; i < text.length; i++) {
    const c = text[i];

    if (quoted) {
      if (c === '"' && text[i + 1] === '"') {
        field += '"';
        i++;
      } else if (c === '"') {
        quoted = false;
      } else {
        field += c;
      }
    } else if (c === '"' && field.length === 0) {
      quoted = true;
    } else if (c === ",") {
      row.push(field);
      field = "";
    } else if (c === "\n") {
      row.push(field);

      if (row.some(value => value.trim() !== "")) {
        rows.push(row);
      }

      row = [];
      field = "";
    } else if (c !== "\r") {
      field += c;
    }
  }

  if (quoted) {
    throw Error("CSV contains an unclosed quotation mark.");
  }

  row.push(field);

  if (row.some(value => value.trim() !== "")) {
    rows.push(row);
  }

  if (rows.length < 2) {
    throw Error("CSV needs a header and at least one data row.");
  }

  if (rows.length > 250001) {
    throw Error("Maximum 250,000 data rows per file.");
  }

  const headers = rows.shift().map(value => value.trim());

  if (headers.some(header => !header)) {
    throw Error("Empty column name detected.");
  }

  if (new Set(headers.map(header => header.toLowerCase())).size !== headers.length) {
    throw Error("Duplicate column names detected.");
  }

  return rows.map((values, index) => {
    if (values.length !== headers.length) {
      throw Error(
        `CSV row ${index + 2} has an incorrect number of columns.`
      );
    }

    return Object.fromEntries(
      headers.map((header, columnIndex) => [
        header,
        values[columnIndex].trim()
      ])
    );
  });
}

function findColumn(headers, terms) {
  return headers.find(header => {
    const normalized = header.toLowerCase().replace(/[\s_-]/g, "");
    return terms.some(term => normalized.includes(term));
  });
}

function refOf(value) {
  return String(value ?? "").trim().toUpperCase();
}

function amountOf(value) {
  const cleaned = String(value ?? "").replace(/[₹$,\s]/g, "");

  if (!/^-?\d+(\.\d{1,2})?$/.test(cleaned)) {
    return null;
  }

  const number = Number(cleaned);

  return Number.isFinite(number)
    ? Math.round(number * 100)
    : null;
}

function money(cents) {
  if (cents === null || cents === undefined) {
    return "—";
  }

  return (cents / 100).toLocaleString("en-IN", {
    style: "currency",
    currency: "INR"
  });
}

function safeText(value) {
  return String(value ?? "").replace(/[&<>"']/g, character => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  })[character]);
}

async function readCSV(file) {
  if (!file) {
    throw Error("Select both CSV files.");
  }

  if (file.size > 20 * 1024 * 1024) {
    throw Error("Each file must be 20 MB or smaller.");
  }

  return parseCSV(await file.text());
}

/* ---------------- RECONCILIATION ENGINE ---------------- */

function reconcile(payments, bank) {
  const paymentHeaders = Object.keys(payments[0] || {});
  const bankHeaders = Object.keys(bank[0] || {});

  const paymentReferenceColumn = findColumn(paymentHeaders, [
    "paymentreference",
    "transactionreference",
    "reference",
    "transactionid",
    "txn"
  ]);

  const paymentAmountColumn = findColumn(paymentHeaders, [
    "paymentamount",
    "transactionamount",
    "amount",
    "paid"
  ]);

  const bankReferenceColumn = findColumn(bankHeaders, [
    "bankreference",
    "transactionreference",
    "reference",
    "transactionid",
    "txn"
  ]);

  const bankAmountColumn = findColumn(bankHeaders, [
    "bankamount",
    "transactionamount",
    "amount",
    "credit",
    "debit"
  ]);

  if (
    !paymentReferenceColumn ||
    !paymentAmountColumn ||
    !bankReferenceColumn ||
    !bankAmountColumn
  ) {
    throw Error(
      "Cannot detect reference and amount columns. Use payment_reference, payment_amount, bank_reference, bank_amount."
    );
  }

  const paymentRows = payments.map((record, index) => ({
    ref: refOf(record[paymentReferenceColumn]),
    amount: amountOf(record[paymentAmountColumn]),
    index
  }));

  const bankRows = bank.map((record, index) => ({
    ref: refOf(record[bankReferenceColumn]),
    amount: amountOf(record[bankAmountColumn]),
    index
  }));

  const paymentCounts = new Map();
  const bankCounts = new Map();
  const bankMap = new Map();

  paymentRows.forEach(record => {
    if (record.ref) {
      paymentCounts.set(
        record.ref,
        (paymentCounts.get(record.ref) || 0) + 1
      );
    }
  });

  bankRows.forEach(record => {
    if (record.ref) {
      bankCounts.set(
        record.ref,
        (bankCounts.get(record.ref) || 0) + 1
      );

      if (!bankMap.has(record.ref)) {
        bankMap.set(record.ref, []);
      }

      bankMap.get(record.ref).push(record);
    }
  });

  const output = [];

  paymentRows.forEach(record => {
    let matchedBank = null;
    let status;

    if (!record.ref || record.amount === null) {
      status = "Data-quality issue";
    } else if (paymentCounts.get(record.ref) > 1) {
      status = "Duplicate payment reference";
    } else if ((bankCounts.get(record.ref) || 0) > 1) {
      status = "Duplicate bank reference";
    } else if (!bankMap.has(record.ref)) {
      status = "Missing in bank";
    } else {
      matchedBank = bankMap.get(record.ref)[0];

      if (matchedBank.amount === null) {
        status = "Invalid bank amount";
      } else if (matchedBank.amount === record.amount) {
        status = "Matched";
      } else {
        status = "Amount mismatch";
      }
    }

    output.push({
      ref: record.ref || "(missing reference)",
      payment: record.amount,
      bank: matchedBank ? matchedBank.amount : null,
      status
    });
  });

  bankRows.forEach(record => {
    if (!record.ref || record.amount === null) {
      output.push({
        ref: record.ref || "(missing reference)",
        payment: null,
        bank: record.amount,
        status: "Bank data-quality issue"
      });
    } else if (!paymentCounts.has(record.ref)) {
      output.push({
        ref: record.ref,
        payment: null,
        bank: record.amount,
        status: "Bank-only transaction"
      });
    } else if (bankCounts.get(record.ref) > 1) {
      output.push({
        ref: record.ref,
        payment: null,
        bank: record.amount,
        status: "Duplicate bank reference"
      });
    }
  });

  return output;
}

/* ---------------- RECONCILIATION STATUS CHART ---------------- */

function drawBars(id, items) {
  const container = $(id);
  const maximum = Math.max(1, ...items.map(item => item.value));

  container.innerHTML = items.length
    ? items.map(item => {
        const percentage = item.value / maximum * 100;

        return `
          <div class="chart-row">
            <div class="chart-label">
              <span>${safeText(item.label)}</span>
              <strong>${item.value.toLocaleString("en-IN")}</strong>
            </div>

            <div
              class="bar-track"
              role="img"
              aria-label="${safeText(item.label)}: ${item.value}"
            >
              <div
                class="bar-fill ${item.color || ""}"
                style="width:${percentage}%"
              ></div>
            </div>
          </div>
        `;
      }).join("")
    : '<p class="muted">No data available.</p>';
}

/* ---------------- DISCREPANCY PIE CHART ---------------- */

function drawPieChart(id, items) {
  const container = $(id);
  const total = items.reduce((sum, item) => sum + item.value, 0);

  if (!total) {
    container.innerHTML = `
      <p class="muted">No discrepancies found. All result rows are matched.</p>
    `;
    return;
  }

  let currentAngle = 0;

  const segments = items.map((item, index) => {
    const start = currentAngle;
    currentAngle += item.value / total * 360;

    return {
      ...item,
      color: PIE_COLORS[index % PIE_COLORS.length],
      start,
      end: currentAngle,
      percent: (item.value / total * 100).toFixed(1)
    };
  });

  const gradient = segments.map(segment =>
    `${segment.color} ${segment.start}deg ${segment.end}deg`
  ).join(", ");

  container.innerHTML = `
    <div class="pie-layout">
      <div
        class="discrepancy-pie"
        role="img"
        aria-label="Pie chart showing ${total} exception rows across ${items.length} categories"
        style="background:conic-gradient(${gradient})"
      ></div>

      <div>
        <div class="pie-legend">
          ${segments.map(segment => `
            <div class="pie-legend-item">
              <span
                class="pie-swatch"
                style="background:${segment.color}"
              ></span>

              <span class="pie-legend-label">
                ${safeText(segment.label)}
                <span class="pie-percent">${segment.percent}%</span>
              </span>

              <span class="pie-legend-value">${segment.value}</span>
            </div>
          `).join("")}
        </div>

        <div class="pie-total">
          Total exception rows:
          <strong>${total}</strong>
        </div>
      </div>
    </div>
  `;
}

/* ---------------- AMOUNT COMPARISON CARDS ---------------- */

function renderAmountComparison() {
  const container = $("amount-chart");

  const amounts = results
    .filter(record =>
      record.payment !== null && record.bank !== null
    )
    .slice(0, 10);

  if (!amounts.length) {
    container.innerHTML = `
      <p class="muted">No rows with both amounts available.</p>
    `;
    return;
  }

  container.innerHTML = amounts.map(record => {
    const difference = record.payment - record.bank;
    const balanced = difference === 0;

    return `
      <article class="amount-item">
        <div class="amount-ref">
          ${safeText(record.ref)}
        </div>

        <div class="amount-column">
          <span class="amount-heading">Payment amount</span>
          <span class="amount-value">
            ${safeText(money(record.payment))}
          </span>
        </div>

        <div class="amount-column">
          <span class="amount-heading">Bank amount</span>
          <span class="amount-value bank-value">
            ${safeText(money(record.bank))}
          </span>
        </div>

        <div class="amount-difference ${
          balanced ? "balanced" : "has-difference"
        }">
          ${
            balanced
              ? "✓ Amounts match"
              : `Difference: ${safeText(money(difference))}`
          }
        </div>
      </article>
    `;
  }).join("");
}

/* ---------------- KPI AND DASHBOARD ---------------- */

function renderDashboard() {
  const counts = {};

  results.forEach(record => {
    counts[record.status] = (counts[record.status] || 0) + 1;
  });

  const matched = counts.Matched || 0;
  const unmatched = results.length - matched;

  const paymentTotal = results.reduce(
    (sum, record) => sum + (record.payment ?? 0), 0
  );

  const bankTotal = results.reduce(
    (sum, record) => sum + (record.bank ?? 0), 0
  );

  const duplicates =
    (counts["Duplicate payment reference"] || 0) +
    (counts["Duplicate bank reference"] || 0);

  const matchRate = results.length
    ? (matched / results.length * 100).toFixed(1)
    : "0.0";

  const difference = paymentTotal - bankTotal;

  const kpis = [
    ["Total result rows", results.length, ""],
    ["Matched transactions", matched, "good"],
    ["Match rate", `${matchRate}%`, "good"],
    ["Unmatched transactions", unmatched, "warning"],
    ["Amount mismatches", counts["Amount mismatch"] || 0, "danger"],
    ["Missing in bank", counts["Missing in bank"] || 0, "warning"],
    ["Bank-only transactions", counts["Bank-only transaction"] || 0, "warning"],
    ["Duplicate flags", duplicates, "danger"],
    ["Payment total", money(paymentTotal), ""],
    ["Bank total", money(bankTotal), ""],
    ["Financial difference", money(difference), difference === 0 ? "good" : "danger"]
  ];

  $("dashboard-kpis").innerHTML = kpis.map(([label, value, color]) => `
    <div class="kpi ${color}">
      <div class="kpi-label">${safeText(label)}</div>
      <div class="kpi-value">${safeText(value)}</div>
    </div>
  `).join("");

  drawBars("reconciliation-chart", [
    { label: "Matched", value: matched, color: "good" },
    { label: "Unmatched", value: unmatched, color: "warning" }
  ]);

  const discrepancies = Object.entries(counts)
    .filter(([status]) => status !== "Matched")
    .map(([label, value]) => ({ label, value }));

  drawPieChart("discrepancy-chart", discrepancies);
  renderAmountComparison();

  const filter = $("status-filter");
  const previous = filter.value;

  const statuses = [...new Set(results.map(record => record.status))].sort();

  filter.innerHTML = `
    <option value="ALL">All statuses</option>
    ${statuses.map(status => `
      <option value="${safeText(status)}">${safeText(status)}</option>
    `).join("")}
  `;

  filter.value = statuses.includes(previous) ? previous : "ALL";

  renderTable();
}

/* ---------------- TRANSACTION TABLE ---------------- */

function renderTable() {
  const status = $("status-filter").value;
  const query = $("search-filter").value.trim().toLowerCase();

  const filtered = results.filter(record =>
    (status === "ALL" || record.status === status) &&
    record.ref.toLowerCase().includes(query)
  );

  $("table-count").textContent =
    `${filtered.length} of ${results.length} result rows`;

  $("rows").innerHTML = filtered.length
    ? filtered.map(record => {
        let pillClass = "";

        if (record.status === "Matched") {
          pillClass = "matched";
        } else if (/mismatch|duplicate/i.test(record.status)) {
          pillClass = "mismatch";
        } else if (/missing|bank-only/i.test(record.status)) {
          pillClass = "missing";
        }

        return `
          <tr>
            <td>${safeText(record.ref)}</td>
            <td>${safeText(money(record.payment))}</td>
            <td>${safeText(money(record.bank))}</td>
            <td>
              <span class="status-pill ${pillClass}">
                ${safeText(record.status)}
              </span>
            </td>
          </tr>
        `;
      }).join("")
    : `
      <tr>
        <td colspan="4">No transactions match your filters.</td>
      </tr>
    `;
}

/* ---------------- FILE SELECTION ---------------- */

function updateButton() {
  const hasBoth =
    $("payments").files.length > 0 &&
    $("bank").files.length > 0;

  $("run").disabled = !hasBoth;

  $("payment-name").textContent =
    $("payments").files[0]?.name || "No file selected";

  $("bank-name").textContent =
    $("bank").files[0]?.name || "No file selected";

  if (hasBoth) {
    $("status").textContent =
      "Both files selected. Click Reconcile files.";
  } else {
    $("status").textContent =
      "Select both CSV files to begin.";
  }
}

$("payments").addEventListener("change", updateButton);
$("bank").addEventListener("change", updateButton);

$("status-filter").addEventListener("change", renderTable);
$("search-filter").addEventListener("input", renderTable);

/* ---------------- RUN RECONCILIATION ---------------- */

$("run").addEventListener("click", async () => {
  $("run").disabled = true;
  $("status").textContent =
    "Processing files locally in your browser...";

  try {
    const payments = await readCSV($("payments").files[0]);
    const bank = await readCSV($("bank").files[0]);

    results = reconcile(payments, bank);

    renderDashboard();
    $("results").hidden = false;

    $("status").textContent =
      "Reconciliation complete. Review the results below.";

    $("results").scrollIntoView({
      behavior: "smooth",
      block: "start"
    });
  } catch (error) {
    results = [];
    $("results").hidden = true;

    $("status").textContent =
      "Could not reconcile: " + error.message;
  } finally {
    $("run").disabled = !(
      $("payments").files.length &&
      $("bank").files.length
    );
  }
});

/* ---------------- DOWNLOAD CSV REPORT ---------------- */

$("download").addEventListener("click", () => {
  const cell = value => {
    let string = String(value ?? "");

    if (/^[\s]*[=+\-@]/.test(string)) {
      string = "'" + string;
    }

    return '"' + string.replace(/"/g, '""') + '"';
  };

  const lines = [
    ["Reference", "Payment amount INR", "Bank amount INR", "Status"],
    ...results.map(record => [
      record.ref,
      record.payment === null ? "" : (record.payment / 100).toFixed(2),
      record.bank === null ? "" : (record.bank / 100).toFixed(2),
      record.status
    ])
  ];

  const blob = new Blob(
    [
      "\uFEFF" +
      lines.map(row => row.map(cell).join(",")).join("\r\n")
    ],
    { type: "text/csv;charset=utf-8" }
  );

  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");

  link.href = url;
  link.download = "reconcileai_results.csv";
  document.body.appendChild(link);
  link.click();
  link.remove();

  setTimeout(() => URL.revokeObjectURL(url), 1000);
});

/* ---------------- CLEAR ALL DATA ---------------- */

$("clear").addEventListener("click", () => {
  results = [];

  $("payments").value = "";
  $("bank").value = "";

  $("payment-name").textContent = "No file selected";
  $("bank-name").textContent = "No file selected";

  $("dashboard-kpis").replaceChildren();
  $("reconciliation-chart").replaceChildren();
  $("discrepancy-chart").replaceChildren();
  $("amount-chart").replaceChildren();
  $("rows").replaceChildren();

  $("table-count").textContent = "";
  $("results").hidden = true;

  $("status-filter").innerHTML =
    '<option value="ALL">All statuses</option>';

  $("search-filter").value = "";

  $("status").textContent =
    "Cleared. Select both CSV files to begin.";

  updateButton();
});
