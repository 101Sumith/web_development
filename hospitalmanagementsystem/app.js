const state = { page: "dashboard", patients: [], doctors: [], appointments: [], departments: [], user: null, patientPages: 1, patientPage: 1, patientSort: "name:asc", doctorSearch: "", patientSearch: "", appointmentSearch: "", moduleSearch: "" };
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const colors = ["mini-avatar-0", "mini-avatar-1", "mini-avatar-2", "mini-avatar-3", "mini-avatar-4"];
let editing = null;

async function api(path, options = {}) {
  const response = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
  const body = await response.json().catch(() => ({}));
  if(response.status===401&&!path.startsWith("/api/auth/")) { state.user=null; showAuth(false); }
  if (!response.ok) throw new Error(body.error || `Request failed (${response.status})`);
  return body;
}

function initials(name = "") { return name.split(/\s+/).filter(Boolean).slice(0, 2).map(part => part[0].toUpperCase()).join("") || "??"; }
function escapeHtml(value = "") { return String(value).replace(/[&<>"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]); }
function colorClass(name = "") { return colors[[...name].reduce((sum, char) => sum + char.charCodeAt(0), 0) % colors.length]; }
function patientAvatar(name, extra = "") { return `<span class="avatar ${colorClass(name)} ${extra}">${escapeHtml(initials(name))}</span>`; }
function formatDate(value, options = { month: "short", day: "numeric", year: "numeric" }) {
  if (!value) return "—";
  const date = new Date(`${value}T12:00:00`);
  return Number.isNaN(date.getTime()) ? "—" : new Intl.DateTimeFormat(undefined, options).format(date);
}
function formatTime(value) {
  if (!value) return "";
  const [hours, minutes] = value.split(":").map(Number);
  return new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(new Date(2000, 0, 1, hours, minutes));
}
function safeText(value) { return escapeHtml(value || "—"); }
function statusBadge(status) { return `<span class="status status-${escapeHtml(status)}">${escapeHtml(status)}</span>`; }
function person(name, subtitle) { return `<div class="person-cell">${patientAvatar(name)}<div class="person-meta"><strong>${safeText(name)}</strong><span>${safeText(subtitle)}</span></div></div>`; }
function setRows(target, html, empty) {
  const body = $(target);
  body.innerHTML = html;
  if (empty) empty.classList.toggle("hidden", Boolean(html));
}
function showToast(message, error = false) {
  const toast = document.createElement("div");
  toast.className = `toast${error ? " error" : ""}`;
  toast.textContent = message;
  $("#toast-region").append(toast);
  setTimeout(() => toast.remove(), 3500);
}

function money(cents, currency = "USD") {
  try { return new Intl.NumberFormat(undefined, { style: "currency", currency }).format((cents || 0) / 100); }
  catch { return `${currency} ${((cents || 0) / 100).toFixed(2)}`; }
}
function moneyTotals(rows=[]) { return rows.length?rows.map(item=>money(item.total_cents,item.currency)).join(" · "):money(0); }
function localDate(value = new Date()) {
  return `${value.getFullYear()}-${String(value.getMonth()+1).padStart(2,"0")}-${String(value.getDate()).padStart(2,"0")}`;
}

async function refreshDashboard() {
  const data = await api("/api/dashboard");
  $("#stat-patients").textContent = data.stats.patients;
  $("#stat-today").textContent = data.stats.today_appointments;
  $("#upcoming-count").textContent = data.stats.upcoming;
  $("#stat-admissions").textContent = data.stats.admissions;
  $("#stat-occupied-beds").textContent = `${data.stats.occupied_beds} / ${data.stats.beds}`;
  $("#stat-revenue").textContent = moneyTotals(data.stats.revenue_received);
  $("#stat-outstanding").textContent = moneyTotals(data.stats.billing_outstanding);
  $("#data-mode-banner").classList.toggle("hidden", data.data_mode !== "demo");
  const todayRows = data.today.map(appointment => `<tr><td>${person(appointment.patient_name, appointment.patient_id)}</td><td>${safeText(appointment.doctor_name)}</td><td>${formatTime(appointment.time)}</td><td>${safeText(appointment.department)}</td><td>${statusBadge(appointment.status)}</td></tr>`).join("");
  setRows("#today-appointments", todayRows, $("#today-empty"));
  const recentRows = data.recent.map(appointment => `<tr><td>${person(appointment.patient_name, appointment.patient_id)}</td><td>${safeText(appointment.doctor_name)}</td><td>${formatDate(appointment.date, { month: "short", day: "numeric" })} · ${formatTime(appointment.time)}</td><td>${safeText(appointment.department)}</td><td>${statusBadge(appointment.status)}</td><td><button class="table-action" aria-label="Appointment actions" data-appointment-menu="${appointment.id}">···</button></td></tr>`).join("");
  setRows("#recent-appointments", recentRows);
  const departments = Object.entries(data.departments).sort((a, b) => b[1] - a[1]).slice(0, 5);
  const max = Math.max(1, ...departments.map(item => item[1]));
  $("#department-list").innerHTML = departments.length ? departments.map(([name, count]) => `<div class="department-item"><span class="dept-name">${safeText(name)}</span><span class="dept-count">${count} visits</span><div class="dept-bar"><span style="width:${Math.max(6, count / max * 100)}%"></span></div></div>`).join("") : `<p class="page-subtitle">No appointment activity yet.</p>`;
  const trendDays = [];
  for (let offset = 6; offset >= 0; offset--) {
    const day = new Date(); day.setDate(day.getDate() - offset);
    const iso = localDate(day);
    trendDays.push({ iso, label: new Intl.DateTimeFormat(undefined,{weekday:"short"}).format(day), count: data.trends.find(item => item.date === iso)?.count || 0 });
  }
  const trendMax = Math.max(1,...trendDays.map(day => day.count));
  const points = trendDays.map((day,index) => `${18+index*51},${95-day.count/trendMax*65}`).join(" ");
  const area = `${points} 324,96 18,96`;
  $("#visits-chart").innerHTML = `<svg viewBox="0 0 342 118" role="img" aria-label="Appointments over the last seven days">${[25,50,75].map(y=>`<line class="chart-gridline" x1="13" y1="${y}" x2="329" y2="${y}"/>`).join("")}<defs><linearGradient id="visit-fill" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#35aa91" stop-opacity=".2"/><stop offset="1" stop-color="#35aa91" stop-opacity="0"/></linearGradient></defs><polygon class="chart-fill" points="${area}"/><polyline class="chart-line" points="${points}"/>${trendDays.map((day,index)=>`<circle class="chart-point" cx="${18+index*51}" cy="${95-day.count/trendMax*65}" r="3.5"><title>${day.label}: ${day.count} visits</title></circle><text class="chart-label" x="${18+index*51}" y="112" text-anchor="middle">${escapeHtml(day.label)}</text>`).join("")}</svg>`;
  $("#upcoming-list").innerHTML = data.upcoming.length ? data.upcoming.map(item=>`<div class="upcoming-item"><span class="upcoming-time">${item.date===localDate() ? formatTime(item.time) : formatDate(item.date,{month:"short",day:"numeric"})}</span><div class="upcoming-meta"><strong>${safeText(item.patient_name)}</strong><span>${safeText(item.doctor_name)} · ${safeText(item.department)}</span></div>${statusBadge(item.status)}</div>`).join("") : `<div class="upcoming-empty">No upcoming appointments on the schedule.</div>`;
  $("#admission-list").innerHTML = data.admissions_today.length ? data.admissions_today.map(item=>`<div class="upcoming-item"><span class="upcoming-time">${safeText(item.bed_number || "—")}</span><div class="upcoming-meta"><strong>${safeText(item.patient_name)}</strong><span>${safeText(item.ward || "Bed unassigned")} · ${safeText(item.diagnosis)}</span></div>${statusBadge("active")}</div>`).join("") : `<div class="upcoming-empty">No active admissions recorded.</div>`;
}

async function loadPatients() {
  const filter = $("#patient-filter")?.value || "active";
  const [sort,direction]=state.patientSort.split(":");
  const data = await api(`/api/patients?q=${encodeURIComponent(state.patientSearch)}&include_inactive=${filter === "all"}&page=${state.patientPage}&page_size=20&sort=${sort}&direction=${direction}`);
  state.patients = data.items;
  state.patientPages=data.pages;
  $("#patient-count").textContent = data.count;
  const rows = state.patients.map(patient => `<tr><td>${person(patient.name, patient.email)}</td><td><button class="inline-link" data-view-patient="${patient.id}">${safeText(patient.patient_code)}</button></td><td>${safeText(patient.phone)}</td><td>${patient.age ?? "—"} / ${safeText(patient.gender || "—")}</td><td>${patient.last_visit ? formatDate(patient.last_visit, { month: "short", day: "numeric", year: "numeric" }) : "—"}</td><td>${statusBadge(patient.active ? "active" : "inactive")}</td><td><button class="table-action" aria-label="Edit ${escapeHtml(patient.name)}" data-edit-patient="${patient.id}">···</button></td></tr>`).join("");
  setRows("#patients-table", rows, $("#patients-empty"));
  $("#patient-pagination").innerHTML = `<span>Page ${data.page} of ${data.pages} · ${data.count} records</span><div><button class="module-action" data-patient-page="${Math.max(1,data.page-1)}" ${data.page<=1?"disabled":""}>Previous</button> <button class="module-action" data-patient-page="${Math.min(data.pages,data.page+1)}" ${data.page>=data.pages?"disabled":""}>Next</button></div>`;
}

async function loadDoctors() {
  const filter = $("#doctor-filter")?.value || "active";
  state.doctors = await api(`/api/doctors?q=${encodeURIComponent(state.doctorSearch)}&include_inactive=${filter === "all"}`);
  $("#doctor-count").textContent = state.doctors.length;
  const cards = state.doctors.map(doctor => `<article class="doctor-card"><div class="doctor-card-top"><span class="doctor-avatar ${colorClass(doctor.name)}">${escapeHtml(initials(doctor.name))}</span>${statusBadge(doctor.active ? "active" : "inactive")}</div><h3>${safeText(doctor.name)}</h3><div class="specialty">${safeText(doctor.specialty)}</div><p class="doctor-bio">${safeText(doctor.bio || "Dedicated to providing thoughtful, patient-centered care.")}</p><div class="doctor-details"><span>Department</span><strong>${safeText(doctor.department)}</strong></div><div class="doctor-details"><span>Availability</span><strong>${safeText(doctor.availability||"Not set")}</strong></div><div class="doctor-details"><span>Experience</span><strong>${doctor.experience} years</strong></div><div class="doctor-email">${safeText(doctor.email)}</div><button class="table-action" aria-label="${doctor.active ? "Edit" : "Manage"} ${escapeHtml(doctor.name)}" data-edit-doctor="${doctor.id}">${doctor.active ? "Edit details →" : "Restore or edit →"}</button></article>`).join("");
  $("#doctor-grid").innerHTML = cards;
  $("#doctors-empty").classList.toggle("hidden", Boolean(cards));
}

async function loadAppointments() {
  const status = $("#appointment-filter")?.value || "all";
  const params=new URLSearchParams({q:state.appointmentSearch,status});
  if($("#appointment-from")?.value) params.set("from",$("#appointment-from").value);
  if($("#appointment-to")?.value) params.set("to",$("#appointment-to").value);
  state.appointments = await api(`/api/appointments?${params}`);
  $("#appointment-count").textContent = state.appointments.length;
  const rows = state.appointments.map(appointment => `<tr><td>${person(appointment.patient_name, appointment.patient_id)}</td><td>${safeText(appointment.doctor_name)}</td><td>${formatDate(appointment.date)} · ${formatTime(appointment.time)}</td><td>${safeText(appointment.department)}</td><td>${safeText(appointment.reason)}</td><td>${statusBadge(appointment.status)}</td><td><button class="table-action" aria-label="Update appointment status" data-edit-appointment="${appointment.id}">···</button></td></tr>`).join("");
  setRows("#appointments-table", rows, $("#appointments-empty"));
  $("#appointment-calendar").classList.toggle("hidden",$("#appointment-view").value!=="week");
  $("#appointment-list-view").classList.toggle("hidden",$("#appointment-view").value==="week");
  if($("#appointment-view").value==="week") renderAppointmentCalendar();
}
function renderAppointmentCalendar() {
  const start=new Date(); start.setDate(start.getDate()-start.getDay());
  $("#calendar-grid").innerHTML=Array.from({length:7},(_,index)=>{
    const day=new Date(start); day.setDate(start.getDate()+index);
    const iso=localDate(day);
    const events=state.appointments.filter(item=>item.date===iso);
    return `<section class="calendar-day${iso===localDate()?" calendar-today":""}"><header><span>${new Intl.DateTimeFormat(undefined,{weekday:"short"}).format(day)}</span><strong>${day.getDate()}</strong></header>${events.map(item=>`<button class="calendar-event" data-edit-appointment="${item.id}"><strong>${formatTime(item.time)} · ${safeText(item.patient_name)}</strong><span>${safeText(item.doctor_name)}</span></button>`).join("")||`<p class="calendar-none">No visits</p>`}</section>`;
  }).join("");
}

async function loadPageData(page = state.page) {
  if (page === "dashboard") await refreshDashboard();
  if (page === "patients") await loadPatients();
  if (page === "doctors") await loadDoctors();
  if (page === "appointments") await loadAppointments();
  if (MODULES[page]) await loadModule(page);
}

const MODULES = {
  departments:{title:"Departments",intro:"Department directory and care-team ownership.",add:"Add department",columns:[["name","Department"],["head","Department head"],["extension","Extension"],["description","Service overview"]],fields:[["name","Department"],["head","Department head"],["extension","Extension"],["description","Description","textarea"]]},
  records:{title:"Medical records",intro:"Clinical notes and visit documentation. Access is limited to administrators and clinicians.",add:"New clinical note",columns:[["visit_date","Visit date","date"],["patient_name","Patient"],["doctor_name","Clinician"],["diagnosis","Diagnosis"],["treatment","Treatment"]],fields:[["patient_id","Patient","patient"],["doctor_id","Clinician","doctor"],["visit_date","Visit date","date"],["diagnosis","Diagnosis"],["treatment","Treatment","textarea"],["notes","Clinical notes","textarea"]]},
  admissions:{title:"Admissions & discharges",intro:"Inpatient census and length-of-stay tracking.",add:"Admit patient",columns:[["patient_name","Patient"],["ward","Ward"],["bed_number","Bed"],["admitted_on","Admitted","date"],["diagnosis","Reason"],["status","Status","status"]],fields:[["patient_id","Patient","patient"],["doctor_id","Attending clinician","doctor"],["bed_id","Available bed","bed"],["admitted_on","Admission date","date"],["diagnosis","Admission diagnosis"]]},
  beds:{title:"Wards & beds",intro:"Live bed inventory is based on beds entered into this database; no capacity is assumed.",add:"Add bed",columns:[["bed_number","Bed"],["ward","Ward"],["bed_type","Type"],["patient_name","Current patient"],["status","Availability","status"]],fields:[["bed_number","Bed number"],["ward","Ward"],["bed_type","Bed type"],["notes","Notes","textarea"]]},
  billing:{title:"Billing & invoices",intro:"Invoices, payments, and outstanding balances from recorded billing entries.",add:"Create invoice",columns:[["invoice_number","Invoice"],["patient_name","Patient"],["description","Description"],["amount_cents","Amount","money"],["issued_on","Issued","date"],["due_on","Due","date"],["status","Status","status"]],fields:[["patient_id","Patient","patient"],["description","Description"],["amount","Amount","number"],["currency","Currency","currency"],["issued_on","Issue date","date"],["due_on","Due date","date"],["status","Initial status","invoiceStatus"]]},
  pharmacy:{title:"Pharmacy inventory",intro:"Medicine stock and reorder thresholds. Inventory only reflects items entered by your team.",add:"Add medicine",columns:[["name","Medicine"],["sku","SKU"],["quantity","On hand"],["reorder_level","Reorder at"],["expires_on","Expiry","date"],["low_stock","Stock level","stock"]],fields:[["name","Medicine name"],["sku","SKU"],["quantity","Quantity","number"],["reorder_level","Reorder threshold","number"],["unit","Unit"],["expires_on","Expiry date","date"],["unit_price","Unit price","number"]]},
  laboratory:{title:"Laboratory requests",intro:"Test orders, progress, and recorded results.",add:"Request test",columns:[["ordered_on","Ordered","date"],["patient_name","Patient"],["doctor_name","Ordering clinician"],["test_name","Test"],["status","Status","status"],["result","Result"]],fields:[["patient_id","Patient","patient"],["doctor_id","Ordering clinician","doctor"],["test_name","Test name"],["ordered_on","Order date","date"],["notes","Notes","textarea"]]},
  staff:{title:"Staff & access",intro:"Staff accounts use password-protected, role-scoped access. Share credentials out of band.",add:"Add staff member",columns:[["name","Name"],["email","Email"],["role","Role"],["created_at","Added","date"],["active","Account","active"]],fields:[["name","Full name"],["email","Email","email"],["role","Access role","role"],["password","Initial password","password"]]},
  notifications:{title:"Notifications",intro:"Operational alerts generated for this workspace. Mark each item as read when reviewed.",columns:[["message","Notification"],["category","Type"],["created_at","Received","date"],["read_at","Read","date"]]},
  settings:{title:"Profile & security",intro:"Update your account name or password. Passwords must be at least 12 characters.",fields:[["name","Full name"],["password","New password (leave blank to keep current)","password"]]},
  reports:{title:"Reports & analytics",intro:"Operational reports generated from the records in this database."}
};
const WRITE_ROLES={
  patients:["administrator","receptionist"],doctors:["administrator","receptionist"],appointments:["administrator","doctor","receptionist"],
  departments:["administrator"],records:["administrator","doctor"],admissions:["administrator","doctor","receptionist"],
  beds:["administrator","receptionist"],billing:["administrator","billing"],pharmacy:["administrator","receptionist"],
  laboratory:["administrator","doctor","receptionist"],staff:["administrator"]
};
function canWrite(module) { return Boolean(state.user&&WRITE_ROLES[module]?.includes(state.user.role)); }

function optionList(values, selected="") {
  return values.map(item=>({value:String(item.value),label:item.label,selected:String(item.value)===String(selected)}));
}
function moduleOptions(type) {
  if(type==="patient") return optionList(state.patients.filter(item=>item.active).map(item=>({value:item.id,label:`${item.name} · ${item.patient_code}`})));
  if(type==="doctor") return optionList(state.doctors.filter(item=>item.active).map(item=>({value:item.id,label:`${item.name} · ${item.specialty}`})));
  if(type==="bed") return optionList(state.availableBeds.map(item=>({value:item.id,label:`${item.bed_number} · ${item.ward}`})));
  if(type==="role") return optionList([{value:"doctor",label:"Doctor"},{value:"receptionist",label:"Receptionist"},{value:"billing",label:"Billing"},{value:"administrator",label:"Administrator"}]);
  if(type==="invoiceStatus") return optionList(["draft","issued","paid","void"].map(value=>({value,label:value})));
  if(type==="currency") return optionList(["USD","EUR","GBP","INR","CAD","AUD"].map(value=>({value,label:value})));
  return [];
}
async function loadModule(page) {
  if(page==="settings") {
    const data=await api("/api/modules/settings");
    renderSettings(data.user);
    return;
  }
  if(page==="reports") { await loadReports(); return; }
  const search=state.moduleSearch||"";
  const data=await api(`/api/modules/${page}?q=${encodeURIComponent(search)}`);
  if(page==="settings") { renderSettings(data.user); return; }
  if(page==="reports") { await loadReports(); return; }
  state.moduleItems=data.items||[];
  if(page==="beds") state.availableBeds=state.moduleItems.filter(item=>item.status==="available");
  if(page==="departments") state.departments=state.moduleItems;
  if(page==="notifications") renderNotifications(state.moduleItems);
  else renderModule(page,state.moduleItems);
}
function renderModule(page,items) {
  const config=MODULES[page];
  const cards=[];
  if(page==="beds") {
    const occupied=items.filter(item=>item.status==="occupied").length;
    cards.push(["Registered beds",items.length,"Entered bed records; capacity not inferred."],["Available",items.filter(item=>item.status==="available").length,"Beds currently available."],["Occupied",occupied,"Beds linked to active admissions."]);
  }
  if(page==="pharmacy") cards.push(["Medicines tracked",items.length,"Unique stock items entered."],["Reorder alerts",items.filter(item=>item.low_stock).length,"Items at or below reorder point."]);
  if(page==="billing") cards.push(["Open invoices",items.filter(item=>["draft","issued"].includes(item.status)).length,"Invoices in draft or issued status."],["Paid invoices",items.filter(item=>item.status==="paid").length,"Paid invoice records."]);
  if(page==="admissions") cards.push(["Active admissions",items.filter(item=>item.status==="admitted").length,"Patients currently admitted."],["Discharged",items.filter(item=>item.status==="discharged").length,"Historical admissions."]);
  const toolbar=`<div class="module-toolbar"><div><span class="count-pill">${items.length} records</span></div><div class="module-filters">${page!=="settings"?`<label class="table-search"><svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></svg><input id="module-search" type="search" value="${escapeHtml(state.moduleSearch)}" placeholder="Search ${escapeHtml(config.title.toLowerCase())}..."></label>`:""}${config.add&&canWrite(page)?`<button class="button button-primary" data-module-add="${page}">+ ${escapeHtml(config.add)}</button>`:""}</div></div>`;
  const hasItems=items.length>0;
  const table=hasItems?`<div class="table-wrap module-table"><table class="data-table"><thead><tr>${config.columns.map(([,label])=>`<th>${escapeHtml(label)}</th>`).join("")}<th></th></tr></thead><tbody>${items.map(item=>`<tr>${config.columns.map(([key,label,format])=>`<td>${renderModuleCell(item,key,format)}</td>`).join("")}<td>${renderModuleAction(page,item)}</td></tr>`).join("")}</tbody></table></div>`:`<div class="module-empty">${page==="notifications"?"No notifications have been generated yet. New activity will appear here.":`No ${escapeHtml(config.title.toLowerCase())} records yet. ${canWrite(page)?"Add your first record to get started.":"Records will appear here as your team enters them."}`}</div>`;
  $("#page-module").innerHTML=`<div class="page-heading-row"><div><p class="eyebrow">${escapeHtml(config.title.toUpperCase())}</p><h1>${escapeHtml(config.title)}</h1><p class="page-subtitle">${escapeHtml(config.intro)}</p></div></div>${cards.length?`<div class="module-grid">${cards.map(([title,value,description])=>`<article class="module-card"><h3>${escapeHtml(title)}</h3><span class="module-value">${value}</span><p>${escapeHtml(description)}</p></article>`).join("")}</div>`:""}<section class="panel">${toolbar}${table}</section>`;
  const input=$("#module-search");
  input?.addEventListener("input",debounce(event=>{state.moduleSearch=event.target.value;loadModule(page).catch(error=>showToast(error.message,true));},220));
}
function renderModuleCell(item,key,format) {
  const value=item[key];
  if(format==="date") return safeText(value?formatDate(value,{month:"short",day:"numeric",year:"numeric"}):"—");
  if(format==="money") return safeText(money(item.amount_cents,item.currency));
  if(format==="status") return statusBadge(value||"unknown");
  if(format==="stock") return item.low_stock?`<span class="status status-cancelled">Reorder</span>`:`<span class="status status-completed">In stock</span>`;
  if(format==="active") return statusBadge(value?"active":"inactive");
  return safeText(value||"—");
}
function renderModuleAction(page,item) {
  const id=escapeHtml(item.id);
  if(page==="notifications") return item.read_at?"<span class=\"read-only\">Read</span>":`<button class="module-action" data-module-action="read" data-module-id="${id}">Mark read</button>`;
  if(page==="admissions"&&item.status==="admitted"&&canWrite(page)) return `<button class="module-action" data-module-action="discharge" data-module-id="${id}">Discharge</button>`;
  if(page==="billing"&&item.status==="issued"&&canWrite(page)) return `<button class="module-action" data-module-action="paid" data-module-id="${id}">Mark paid</button>`;
  if(page==="laboratory"&&item.status!=="completed"&&item.status!=="cancelled"&&canWrite(page)) return `<button class="module-action" data-module-action="lab-complete" data-module-id="${id}">Record result</button>`;
  if(page==="records"&&canWrite(page)) return `<button class="module-action" data-module-edit="${page}" data-module-id="${id}">Edit note</button>`;
  if(page==="beds"&&canWrite(page)) return `<button class="module-action" data-module-action="bed-toggle" data-module-id="${id}" data-status="${escapeHtml(item.status)}">${item.status==="maintenance"?"Mark available":item.status==="available"?"Maintenance":"Occupied"}</button>`;
  if(page==="pharmacy"&&canWrite(page)) return `<button class="module-action" data-module-edit="${page}" data-module-id="${id}">Edit stock</button>`;
  if(page==="departments"&&canWrite(page)) return `<button class="module-action" data-module-edit="${page}" data-module-id="${id}">Edit</button>`;
  if(page==="staff"&&canWrite(page)) return item.active?`<button class="module-action" data-module-edit="staff" data-module-id="${id}">Edit</button><button class="module-action" data-module-action="staff-deactivate" data-module-id="${id}">Deactivate</button>`:`<button class="module-action" data-module-action="staff-restore" data-module-id="${id}">Restore</button>`;
  return "";
}
function renderNotifications(items) {
  const read=items.filter(item=>item.read_at).length;
  $("#page-module").innerHTML=`<div class="page-heading-row"><div><p class="eyebrow">WORKSPACE ACTIVITY</p><h1>Notifications</h1><p class="page-subtitle">${items.length-read} unread notifications · Alerts are stored in the workspace database.</p></div></div><section class="panel"><div class="module-toolbar"><span class="count-pill">${items.length} notifications</span></div>${items.length?items.map(item=>`<div class="notification-item${item.read_at?"":" notification-unread"}"><p>${safeText(item.message)}</p><time>${formatDate(item.created_at?.slice(0,10),{month:"short",day:"numeric"})}${item.read_at?" · Read":""}</time>${item.read_at?"":`<button class="module-action" data-module-action="read" data-module-id="${item.id}">Mark read</button>`}</div>`).join(""):`<div class="module-empty">No notifications have been generated yet. New activity will appear here.</div>`}</section>`;
}
async function openPatientProfile(id) {
  try {
    const data=await api(`/api/patients/${encodeURIComponent(id)}`);
    const patient=data.patient;
    editing=null;
    $("#modal-title").textContent=patient.name;
    $("#modal-description").textContent=`${patient.patient_code} · Patient profile and visit history`;
    $("#modal-eyebrow").textContent="PATIENT PROFILE";
    $("#modal-fields").innerHTML=`<div class="module-grid"><article class="module-card"><h3>Contact</h3><p>${safeText(patient.email)}<br>${safeText(patient.phone)}<br>${safeText(patient.address)}</p></article><article class="module-card"><h3>Patient details</h3><p>${patient.age??"—"} years · ${safeText(patient.gender||"Not recorded")}<br>Blood group ${safeText(patient.blood_group||"Not recorded")}<br>${patient.active?"Active record":"Archived record"}</p></article></div><h3 class="profile-section-title">Clinical notes</h3>${data.records.length?data.records.map(item=>`<article class="profile-history"><strong>${formatDate(item.visit_date)} · ${safeText(item.doctor_name)}</strong><p>${safeText(item.diagnosis)}</p><span>${safeText(item.treatment)}</span></article>`).join(""):`<div class="module-empty">No clinical notes have been recorded for this patient.</div>`}<h3 class="profile-section-title">Appointments</h3>${data.appointments.length?data.appointments.map(item=>`<article class="profile-history"><strong>${formatDate(item.date)} · ${formatTime(item.time)}</strong><p>${safeText(item.doctor_name)} · ${safeText(item.department)}</p><span>${safeText(item.reason)} · ${safeText(item.status)}</span></article>`).join(""):`<div class="module-empty">No appointments on record.</div>`}`;
    $("#modal-submit").classList.add("hidden");
    $("#modal-cancel").textContent="Close";
    $("#modal-backdrop").dataset.type="patient-profile";
    $("#modal-backdrop").classList.remove("hidden");
    $("#modal-close").focus();
  } catch(error) { showToast(error.message,true); }
}
async function submitProfile(event) {
  event.preventDefault();
  const form=event.currentTarget;
  const data=Object.fromEntries(new FormData(form).entries());
  try {
    const result=await api("/api/modules/settings",{method:"PUT",body:JSON.stringify(data)});
    state.user=result.user;
    $("#profile-password").value="";
    applyUserProfile();
    showToast("Profile and security settings updated.");
  } catch(error) { showToast(error.message,true); }
}
async function signOut() {
  try {
    await api("/api/auth/logout",{method:"POST",body:JSON.stringify({})});
    state.user=null;
    $(".app-shell").classList.add("hidden");
    showAuth(false);
  } catch(error) { showToast(error.message,true); }
}
function showAuth(setupRequired) {
  $(".app-shell").classList.add("hidden");
  $("#auth-screen").classList.remove("hidden");
  const setup=Boolean(setupRequired);
  $("#auth-eyebrow").textContent=setup?"FIRST-TIME SETUP":"SECURE WORKSPACE";
  $("#auth-title").textContent=setup?"Create your administrator account":"Welcome back";
  $("#auth-copy").textContent=setup?"Set up the first administrator. No default account or password is created.":"Sign in to your Careflow workspace.";
  $("#auth-submit").textContent=setup?"Create secure account":"Sign in";
  $("#auth-screen").dataset.mode=setup?"setup":"login";
  $("#auth-fields").innerHTML=setup?`${field("name","Administrator name","text",{required:true})}${field("email","Work email","email",{required:true})}${field("password","Create password","password",{required:true,placeholder:"At least 12 characters"})}`:`${field("email","Work email","email",{required:true})}${field("password","Password","password",{required:true})}`;
  $("#auth-error").classList.add("hidden");
  $("#auth-fields input")?.focus();
}
async function submitAuth(event) {
  event.preventDefault();
  const form=event.currentTarget;
  if(!form.reportValidity()) return;
  const setup=$("#auth-screen").dataset.mode==="setup";
  const button=$("#auth-submit");
  button.disabled=true;
  try {
    const result=await api(setup?"/api/auth/setup":"/api/auth/login",{method:"POST",body:JSON.stringify(Object.fromEntries(new FormData(form).entries()))});
    state.user=result.user;
    await enterWorkspace();
  } catch(error) {
    $("#auth-error").textContent=error.message;
    $("#auth-error").classList.remove("hidden");
  } finally { button.disabled=false; }
}
async function enterWorkspace() {
  $("#auth-screen").classList.add("hidden");
  $(".app-shell").classList.remove("hidden");
  applyUserProfile();
  try {
    const [patientData,doctors,departments]=await Promise.all([
      api("/api/patients?page=1&page_size=100"),
      state.user.role==="billing"?Promise.resolve([]):api("/api/doctors"),
      api("/api/modules/departments")
    ]);
    state.patients=patientData.items;
    state.doctors=doctors;
    state.departments=departments.items;
    await refreshDashboard();
    navigate("dashboard");
  } catch(error) { showToast(`Could not load the workspace: ${error.message}`,true); }
}
function renderSettings(user) {
  $("#page-module").innerHTML=`<div class="page-heading-row"><div><p class="eyebrow">ACCOUNT &amp; PRIVACY</p><h1>Profile &amp; security</h1><p class="page-subtitle">Manage your sign-in identity and security.</p></div><button class="button button-secondary" id="sign-out">Sign out</button></div><section class="panel settings-panel"><div class="panel-heading"><div><h2>Account details</h2><p>Role-based access is enforced by the server on every API request.</p></div></div><form id="profile-form" class="settings-form"><div class="field"><label for="profile-name">Full name</label><input id="profile-name" name="name" value="${escapeHtml(user.name)}" required></div><div class="field"><label>Email address</label><input value="${escapeHtml(user.email)}" disabled></div><div class="field"><label>Access role</label><input value="${escapeHtml(user.role)}" disabled></div><div class="field"><label for="profile-password">New password</label><input type="password" id="profile-password" name="password" autocomplete="new-password" minlength="12" placeholder="Leave blank to keep the current password"></div><p class="read-only">Passwords are stored as salted scrypt hashes. Staff accounts require administrator access.</p><button class="button button-primary" type="submit">Save account settings</button></form></section><section class="panel security-note"><div class="panel-heading"><div><h2>Local workspace security</h2><p>This development server listens on 127.0.0.1 and uses HttpOnly, SameSite session cookies.</p></div></div><p>Use a unique password. Do not expose this development server to a network or enter real patient information; production use requires HTTPS, key management, backups, audit review, and a compliant hosting environment.</p></section>`;
  $("#profile-form").addEventListener("submit",submitProfile);
  $("#sign-out").addEventListener("click",signOut);
}
function debounce(callback,delay) { let timer; return (...args)=>{clearTimeout(timer);timer=setTimeout(()=>callback(...args),delay);}; }

async function loadReports() {
  const start=$("#report-from")?.value||localDate(new Date(new Date().getFullYear(),new Date().getMonth(),1));
  const end=$("#report-to")?.value||localDate();
  const dept=$("#report-department")?.value||"all";
  const data=await api(`/api/modules/reports?from=${encodeURIComponent(start)}&to=${encodeURIComponent(end)}&department=${encodeURIComponent(dept)}`);
  const total=data.appointments.reduce((sum,row)=>sum+row.count,0);
  const paid=data.revenue.filter(row=>row.status==="paid").map(row=>({currency:row.currency,total_cents:row.total}));
  const grouped={}; data.appointments.forEach(row=>grouped[row.department]=(grouped[row.department]||0)+row.count);
  const maximum=Math.max(1,...Object.values(grouped));
  $("#page-module").innerHTML=`<div class="page-heading-row"><div><p class="eyebrow">OPERATIONAL INTELLIGENCE</p><h1>Reports &amp; analytics</h1><p class="page-subtitle">Appointment activity and invoiced revenue recorded for your selected period.</p></div><button class="button button-secondary" id="report-print">Print report</button></div><section class="panel"><div class="report-controls"><div class="field"><label for="report-from">From</label><input id="report-from" type="date" value="${escapeHtml(start)}"></div><div class="field"><label for="report-to">Through</label><input id="report-to" type="date" value="${escapeHtml(end)}"></div><div class="field"><label for="report-department">Department</label><select id="report-department"><option value="all">All departments</option>${state.departments.map(item=>`<option value="${escapeHtml(item.name)}" ${item.name===dept?"selected":""}>${escapeHtml(item.name)}</option>`).join("")}</select></div><button class="button button-primary" id="report-apply">Apply filters</button><a class="button button-secondary" href="/api/reports/export.csv?from=${encodeURIComponent(start)}&amp;to=${encodeURIComponent(end)}&amp;department=${encodeURIComponent(dept)}" download>Export appointments CSV</a></div><div class="report-summary"><article class="module-card"><h3>Appointments</h3><span class="module-value">${total}</span><p>Booked or completed visits in range</p></article><article class="module-card"><h3>Payments received</h3><span class="module-value">${moneyTotals(paid)}</span><p>Recorded invoice payments in range</p></article><article class="module-card"><h3>Bed occupancy</h3><span class="module-value">${data.occupancy} occupied</span><p>Current active admissions with beds</p></article></div><div class="panel-heading"><div><h2>Department activity</h2><p>Appointments grouped by the recorded department</p></div></div><div class="chart-bars">${Object.entries(grouped).length?Object.entries(grouped).map(([name,value])=>`<div class="chart-bar-column"><div class="chart-bar" style="height:${Math.max(4,value/maximum*110)}px" title="${value} visits"></div><span>${escapeHtml(name)}</span><strong>${value}</strong></div>`).join(""):`<div class="module-empty">No appointment data for this period.</div>`}</div></section>`;
  $("#report-apply").addEventListener("click",()=>loadReports().catch(error=>showToast(error.message,true)));
  $("#report-print").addEventListener("click",()=>window.print());
}
function navigate(page) {
  if (!["dashboard", "patients", "doctors", "appointments"].includes(page) && !MODULES[page]) return;
  const navLink=$$(".nav-link").find(link=>link.dataset.page===page);
  if(state.user&&navLink?.dataset.roles&&!navLink.dataset.roles.split(",").includes(state.user.role)) {
    showToast("Your account does not have access to this section.",true);
    return;
  }
  state.page = page;
  $$(".page-view").forEach(view => view.classList.toggle("active", view.id === `page-${MODULES[page]?"module":page}`));
  $$(".nav-link").forEach(link => link.classList.toggle("active", link.dataset.page === page));
  $("#breadcrumb-current").textContent = MODULES[page]?.title||page[0].toUpperCase() + page.slice(1);
  $("#sidebar").classList.remove("open");
  loadPageData(page).catch(error => showToast(error.message, true));
}

const departments = ["Cardiology", "Dermatology", "Neurology", "Orthopedics", "Pediatrics", "General Medicine", "Ophthalmology", "Oncology", "Other"];
function field(name, label, type = "text", options = {}) {
  const { required = false, full = false, value = "", choices = [], min = "", max = "", placeholder = "", step = "" } = options;
  const id = `field-${name}`;
  let control;
  if (type === "select") control = `<select id="${id}" name="${name}" ${required ? "required" : ""}>${choices.map(choice => `<option value="${escapeHtml(choice.value)}" ${choice.value === value ? "selected" : ""}>${escapeHtml(choice.label)}</option>`).join("")}</select>`;
  else if(type==="textarea") control=`<textarea id="${id}" name="${name}" placeholder="${escapeHtml(placeholder)}" ${required ? "required" : ""}>${escapeHtml(value)}</textarea>`;
  else control = `<input id="${id}" name="${name}" type="${type}" value="${escapeHtml(value)}" placeholder="${escapeHtml(placeholder)}" ${required ? "required" : ""} ${type==="password"&&required?'minlength="12"':""} ${min ? `min="${min}"` : ""} ${max ? `max="${max}"` : ""} ${step ? `step="${step}"` : ""}>`;
  return `<div class="field${full ? " full" : ""}"><label for="${id}">${label}${required ? " *" : ""}</label>${control}</div>`;
}
function departmentField(value = "") {
  const choices=(state.departments.length?state.departments.map(item=>item.name):departments).map(item=>({value:item,label:item}));
  if(value&&!choices.some(item=>item.value===value)) choices.push({value,label:value});
  return field("department", "Department", "select", { required: true, value, choices });
}
function suggestedAppointmentSlot() {
  const start=new Date();
  start.setMinutes(Math.ceil((start.getMinutes()+1)/30)*30,0,0);
  if(start.getHours()<9||start.getHours()>=17) { start.setDate(start.getDate()+1); start.setHours(9,0,0,0); }
  while(start.getDay()===0||start.getDay()===6) { start.setDate(start.getDate()+1); start.setHours(9,0,0,0); }
  return {date:localDate(start),time:`${String(start.getHours()).padStart(2,"0")}:${String(start.getMinutes()).padStart(2,"0")}`};
}
function moduleModalFields(module,item) {
  const config=MODULES[module];
  if(!config?.fields) return [];
  return config.fields.map(([name,label,type="text"])=>{
    const value=item?.[name]??(name==="admitted_on"||name==="visit_date"||name==="ordered_on"||name==="issued_on"?localDate():name==="due_on"?localDate(new Date(Date.now()+14*86400000)):name==="currency"?"USD":name==="unit"?"units":name==="status"?"issued":name==="reorder_level"?10:"");
    const required=!["head","extension","description","treatment","notes","doctor_id","bed_id","expires_on","appointment_id"].includes(name)&&(name!=="password"||!item);
    if(type==="patient"||type==="doctor"||type==="bed"||type==="role"||type==="currency"||type==="invoiceStatus") {
      const options=moduleOptions(type);
      if(name==="doctor_id"||name==="bed_id") options.unshift({value:"",label:"Unassigned / not selected",selected:!value});
      return field(name,label,"select",{required:required&&type!=="bed"&&type!=="doctor",value,choices:options.map(option=>({value:option.value,label:option.label}))});
    }
    return field(name,label,type,{required,full:type==="textarea",value,min:type==="number"?(name==="password"?"12":"0"):"",step:name==="amount"||name==="unit_price"?"0.01":"",placeholder:name==="password"?"At least 12 characters":""});
  });
}
function openModal(type, item = null) {
  editing = item ? { type, id: item.id } : null;
  const fields = [];
  let title = "", description = "", submit = "";
  if (type === "patient") {
    title = item ? "Edit patient" : "Add a patient"; description = item ? "Update this patient’s details." : "Create a patient record."; submit = item ? "Save changes" : "Save patient";
    fields.push(field("name", "Full name", "text", { required: true, full: true, value: item?.name || "" }));
    fields.push(field("email", "Email address", "email", { required: true, value: item?.email || "" }));
    fields.push(field("phone", "Phone number", "tel", { required: true, value: item?.phone || "" }));
    fields.push(field("date_of_birth", "Date of birth", "date", { value: item?.date_of_birth || "", max: new Date().toISOString().slice(0, 10) }));
    fields.push(field("gender", "Gender", "select", { value: item?.gender || "Prefer not to say", choices: ["Female", "Male", "Non-binary", "Prefer not to say"].map(value => ({ value, label: value })) }));
    fields.push(field("blood_group", "Blood group", "select", { value: item?.blood_group || "", choices: ["", "A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"].map(value => ({ value, label: value || "Not specified" })) }));
    fields.push(field("address", "Address", "text", { full: true, value: item?.address || "" }));
  } else if (type === "doctor") {
    title = item ? "Edit doctor" : "Add a doctor"; description = item ? "Update this doctor’s profile." : "Add a new member to your care team."; submit = item ? "Save changes" : "Save doctor";
    fields.push(field("name", "Full name", "text", { required: true, full: true, value: item?.name || "" }));
    fields.push(field("specialty", "Specialty", "text", { required: true, value: item?.specialty || "" }));
    fields.push(departmentField(item?.department || ""));
    fields.push(field("email", "Email address", "email", { required: true, value: item?.email || "" }));
    fields.push(field("phone", "Phone number", "tel", { required: true, value: item?.phone || "" }));
    fields.push(field("experience", "Years of experience", "number", { required: true, value: item?.experience ?? "", min: "0", max: "80" }));
    fields.push(field("bio", "Short bio", "text", { full: true, value: item?.bio || "" }));
    fields.push(field("availability","Availability","text",{full:true,value:item?.availability||"Weekdays, 9 AM – 5 PM",placeholder:"Weekdays, 9 AM – 5 PM"}));
  } else if(type==="module-lab-result") {
    title="Record laboratory result";description=`Update ${item.test_name} for ${item.patient_name}.`;submit="Save result";
    fields.push(field("status","Result status","select",{required:true,value:"completed",choices:["in_progress","completed","cancelled"].map(value=>({value,label:value.replace("_"," ")}))}));
    fields.push(field("result","Result","textarea",{full:true,value:item.result||"",placeholder:"Enter the verified result"}));
  } else if(type.startsWith("module-")) {
    const module=type.slice(7);
    const config=MODULES[module];
    title=item?`Update ${config.title.toLowerCase()}`:config.add||`Update ${config.title.toLowerCase()}`;
    description=`Changes are stored in the hospital database.`;
    submit=item?"Save changes":`Save ${config.title.toLowerCase()}`;
    fields.push(...moduleModalFields(module,item));
  } else {
    title = item?"Reschedule appointment":"New appointment"; description = "Schedule a visit with one of your doctors."; submit = item?"Save new time":"Book appointment";
    const slot=suggestedAppointmentSlot();
    fields.push(field("patient_id", "Patient", "select", { required: true,value:item?.patient_id||"", choices: state.patients.filter(patient => patient.active).map(patient => ({ value: patient.id, label: `${patient.name} · ${patient.patient_code}` })) }));
    fields.push(field("doctor_id", "Doctor", "select", { required: true,value:item?.doctor_id||"", choices: state.doctors.filter(doctor => doctor.active).map(doctor => ({ value: doctor.id, label: `${doctor.name} · ${doctor.specialty}` })) }));
    fields.push(field("date", "Date", "date", { required: true, value: item?.date||slot.date, min: localDate() }));
    fields.push(field("time", "Time", "time", { required: true, value: item?.time||slot.time }));
    fields.push(departmentField(item?.department||state.doctors.find(doctor=>String(doctor.id)===String(item?.doctor_id))?.department||state.doctors.find(doctor => doctor.active)?.department||departments[0]));
    fields.push(field("duration_minutes","Visit length (minutes)","number",{required:true,value:item?.duration_minutes||30,min:"15",max:"240",step:"15"}));
    fields.push(field("reason", "Reason for visit", "text", { full: true, value: item?.reason||"", placeholder: "e.g. Annual checkup" }));
  }
  $("#modal-title").textContent = title;
  $("#modal-description").textContent = description;
  $("#modal-submit").textContent = submit;
  $("#modal-submit").classList.remove("hidden");
  $("#modal-cancel").textContent="Cancel";
  $("#modal-eyebrow").textContent = type === "appointment" ? "SCHEDULE A VISIT" : "CARE MANAGEMENT";
  $("#modal-fields").innerHTML = fields.join("");
  $("#form-error").classList.add("hidden");
  $("#form-error").textContent = "";
  $("#modal-backdrop").classList.remove("hidden");
  $("#modal-backdrop").setAttribute("data-type", type);
  const first = $("#modal-fields input, #modal-fields select");
  first?.focus();
  if (type === "appointment") $("#field-patient_id").addEventListener("change", () => syncAppointmentDepartment(), { once: false });
  if (type === "appointment") $("#field-doctor_id").addEventListener("change", () => syncAppointmentDepartment(), { once: false });
}
function syncAppointmentDepartment() {
  const doctor = state.doctors.find(item => String(item.id) === $("#field-doctor_id")?.value);
  if (doctor && $("#field-department")) $("#field-department").value = doctor.department;
}
function closeModal() { $("#modal-backdrop").classList.add("hidden"); editing = null; }
async function submitModal(event) {
  event.preventDefault();
  const form = event.currentTarget;
  if (!form.reportValidity()) return;
  const type = $("#modal-backdrop").dataset.type;
  const data = Object.fromEntries(new FormData(form).entries());
  const wasEditing=Boolean(editing);
  const module=type.startsWith("module-")?type.slice(7):"";
  const moduleId=type==="module-lab-result"?"laboratory":module;
  const path = moduleId?`/api/modules/${moduleId}${editing?`/${editing.id}`:""}`:editing ? `/api/${type === "appointment" ? "appointments" : `${type}s`}/${editing.id}` : `/api/${type === "appointment" ? "appointments" : `${type}s`}`;
  const method = type==="module-lab-result"?"PATCH":moduleId==="settings"?"PUT":editing ? "PUT" : "POST";
  $("#modal-submit").disabled = true;
  try {
    await api(path, { method, body: JSON.stringify(data) });
    closeModal();
    showToast(type === "appointment" ? wasEditing?"Appointment rescheduled successfully.":"Appointment booked successfully." : `${type[0].toUpperCase()}${type.slice(1)} saved successfully.`);
    await Promise.all([loadPageData(), state.page === "dashboard" ? Promise.resolve() : refreshDashboard()]);
    if(type==="module-settings") { state.user={...state.user,name:data.name}; applyUserProfile(); }
  } catch (error) {
    $("#form-error").textContent = error.message;
    $("#form-error").classList.remove("hidden");
  } finally { $("#modal-submit").disabled = false; }
}

function openActionMenu(button) {
  const patientId = button.dataset.editPatient;
  const doctorId = button.dataset.editDoctor;
  const appointmentId = button.dataset.editAppointment || button.dataset.appointmentMenu;
  if (patientId) {
    const patient = state.patients.find(item => String(item.id) === patientId);
    if (patient) showChoiceMenu(button, [{ label: "Edit patient", run: () => openModal("patient", patient) }, { label: patient.active ? "Archive patient" : "Restore patient", run: () => archiveRecord("patients", patient, !patient.active) }]);
  } else if (doctorId) {
    const doctor = state.doctors.find(item => String(item.id) === doctorId);
    if (doctor) showChoiceMenu(button, [{ label: "Edit doctor", run: () => openModal("doctor", doctor) }, { label: doctor.active ? "Archive doctor" : "Restore doctor", run: () => archiveRecord("doctors", doctor, !doctor.active) }]);
  } else if (appointmentId) {
    const id = appointmentId;
    const appointment=state.appointments.find(item=>String(item.id)===String(id));
    const choices=[];
    if(appointment?.status==="scheduled") choices.push({label:"Reschedule visit",run:()=>openModal("appointment",appointment)});
    if(appointment?.status!=="completed") choices.push({ label: "Mark completed", run: () => updateAppointment(id, "completed") });
    if(appointment?.status==="scheduled") choices.push({ label: "Cancel appointment", run: () => updateAppointment(id, "cancelled") });
    showChoiceMenu(button, choices);
  }
}
function showChoiceMenu(anchor, choices) {
  $$(".action-popover").forEach(node => node.remove());
  const rect = anchor.getBoundingClientRect();
  const menu = document.createElement("div");
  menu.className = "action-popover";
  menu.style.cssText = `position:fixed;z-index:35;top:${Math.min(rect.bottom, innerHeight - 100)}px;right:${Math.max(10, innerWidth - rect.right)}px;min-width:145px;padding:5px;border:1px solid #edf0f4;border-radius:8px;background:#fff;box-shadow:0 7px 24px #26375221`;
  choices.forEach(choice => {
    const option = document.createElement("button");
    option.type = "button"; option.textContent = choice.label;
    option.style.cssText = "display:block;width:100%;padding:9px 10px;border:0;border-radius:5px;text-align:left;color:#536176;background:transparent;font:11px 'DM Sans',sans-serif;cursor:pointer";
    option.addEventListener("click", () => { menu.remove(); choice.run(); });
    menu.append(option);
  });
  document.body.append(menu);
  setTimeout(() => document.addEventListener("click", function dismiss(event) { if (!menu.contains(event.target) && event.target !== anchor) { menu.remove(); document.removeEventListener("click", dismiss); } }, { once: true }), 0);
}
async function archiveRecord(resource, item, active) {
  try {
    await api(`/api/${resource}/${item.id}`, { method: "DELETE", body: JSON.stringify({ active }) });
    showToast(`${resource === "patients" ? "Patient" : "Doctor"} ${active ? "restored" : "archived"}.`);
    await loadPageData();
  } catch (error) { showToast(error.message, true); }
}
async function updateAppointment(id, status) {
  try {
    if(status==="cancelled"&&!window.confirm("Cancel this appointment? This will keep it in the record but release the scheduled time.")) return;
    await api(`/api/appointments/${id}`, { method: "PATCH", body: JSON.stringify({ status }) });
    showToast(`Appointment marked ${status}.`);
    await loadPageData();
  } catch (error) { showToast(error.message, true); }
}

function applyUserProfile() {
  const user=state.user;
  if(!user) return;
  $$(".profile-info strong").forEach(node=>node.textContent=user.name);
  $$(".profile-info span").forEach(node=>node.textContent=user.role);
  $$(".avatar-user").forEach(node=>node.textContent=initials(user.name));
  $$(".nav-link[data-roles]").forEach(link=>link.classList.toggle("hidden",!link.dataset.roles.split(",").includes(user.role)));
  $$('[data-action="new-patient"]').forEach(button=>button.classList.toggle("hidden",!canWrite("patients")));
  $$('[data-action="new-doctor"]').forEach(button=>button.classList.toggle("hidden",!canWrite("doctors")));
  $$('[data-action="new-appointment"]').forEach(button=>button.classList.toggle("hidden",!canWrite("appointments")));
}

async function handleModuleAction(button) {
  const module=state.page, id=button.dataset.moduleId, action=button.dataset.moduleAction;
  try {
    if(action==="read") await api(`/api/modules/notifications/${id}`,{method:"PATCH",body:JSON.stringify({})});
    else if(action==="discharge") {
      if(!window.confirm("Discharge this patient and release the assigned bed?")) return;
      await api(`/api/modules/admissions/${id}`,{method:"PATCH",body:JSON.stringify({discharged_on:localDate()})});
    } else if(action==="paid") {
      if(!window.confirm("Mark this invoice as paid?")) return;
      await api(`/api/modules/billing/${id}`,{method:"PATCH",body:JSON.stringify({status:"paid"})});
    } else if(action==="lab-complete") {
      const item=state.moduleItems.find(row=>String(row.id)===String(id));
      openModal("module-lab-result",{...item,id});
      return;
    } else if(action==="bed-toggle") {
      const item=state.moduleItems.find(row=>String(row.id)===String(id));
      if(item.status==="occupied") { showToast("Discharge the patient before changing an occupied bed.",true); return; }
      const status=item.status==="available"?"maintenance":"available";
      await api(`/api/modules/beds/${id}`,{method:"PATCH",body:JSON.stringify({status})});
    } else if(action==="staff-restore") {
      await api(`/api/modules/staff/${id}`,{method:"PATCH",body:JSON.stringify({active:true})});
    } else if(action==="staff-deactivate") {
      if(!window.confirm("Deactivate this staff account and revoke its sessions?")) return;
      await api(`/api/modules/staff/${id}`,{method:"DELETE",body:JSON.stringify({})});
    }
    showToast("Changes saved.");
    await loadModule(module);
    await refreshDashboard();
  } catch(error) { showToast(error.message,true); }
}

function bindEvents() {
  document.addEventListener("click", event => {
    const pageLink = event.target.closest("[data-page]");
    if (pageLink) { event.preventDefault(); navigate(pageLink.dataset.page); return; }
    const action = event.target.closest("[data-action]");
    if (action) {
      const type = action.dataset.action.replace("new-", "");
      if (type === "appointment") {
        Promise.all([loadPatients(), loadDoctors()]).then(() => openModal("appointment")).catch(error => showToast(error.message, true));
      } else openModal(type);
      return;
    }
    if(event.target.closest("[data-module-add]")) {
      const module=event.target.closest("[data-module-add]").dataset.moduleAdd;
      if(module==="admissions") {
        Promise.all([api("/api/modules/beds"),loadPatients(),loadDoctors()]).then(([beds])=>{
          state.availableBeds=beds.items.filter(item=>item.status==="available");
          openModal(`module-${module}`);
        }).catch(error=>showToast(error.message,true));
        return;
      }
      openModal(`module-${module}`);
      return;
    }
    if(event.target.closest("[data-module-edit]")) {
      const button=event.target.closest("[data-module-edit]");
      const item=state.moduleItems.find(row=>String(row.id)===button.dataset.moduleId);
      if(item) openModal(`module-${button.dataset.moduleEdit}`,item);
      return;
    }
    if(event.target.closest("[data-module-action]")) { handleModuleAction(event.target.closest("[data-module-action]")); return; }
    if(event.target.closest("[data-patient-page]")) {
      const page=Number(event.target.closest("[data-patient-page]").dataset.patientPage);
      if(Number.isInteger(page)&&page>=1&&page<=state.patientPages) { state.patientPage=page; loadPatients().catch(error=>showToast(error.message,true)); }
      return;
    }
    if(event.target.closest("[data-view-patient]")) { openPatientProfile(event.target.closest("[data-view-patient]").dataset.viewPatient); return; }
    const menuButton = event.target.closest("[data-edit-patient], [data-edit-doctor], [data-edit-appointment], [data-appointment-menu]");
    if (menuButton) openActionMenu(menuButton);
  });
  $("#modal-close").addEventListener("click", closeModal);
  $("#modal-cancel").addEventListener("click", closeModal);
  $("#modal-backdrop").addEventListener("click", event => { if (event.target === $("#modal-backdrop")) closeModal(); });
  $("#modal-form").addEventListener("submit", submitModal);
  $("#auth-form").addEventListener("submit",submitAuth);
  document.addEventListener("keydown", event => {
    if (event.key === "Escape") { closeModal(); $("#sidebar").classList.remove("open"); }
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") { event.preventDefault(); $("#global-search-input").focus(); }
  });
  $("#mobile-menu").addEventListener("click", () => $("#sidebar").classList.toggle("open"));
  $("#patient-search").addEventListener("input", debounce(event => { state.patientSearch = event.target.value; state.patientPage=1; loadPatients().catch(error => showToast(error.message, true)); },220));
  $("#patient-filter").addEventListener("change", () => loadPatients().catch(error => showToast(error.message, true)));
  $("#patient-sort").addEventListener("change", event=>{state.patientSort=event.target.value;state.patientPage=1;loadPatients().catch(error=>showToast(error.message,true));});
  $("#doctor-search").addEventListener("input", debounce(event => { state.doctorSearch = event.target.value; loadDoctors().catch(error => showToast(error.message, true)); },220));
  $("#doctor-filter").addEventListener("change", () => loadDoctors().catch(error => showToast(error.message, true)));
  $("#appointment-search").addEventListener("input", debounce(event => { state.appointmentSearch = event.target.value; loadAppointments().catch(error => showToast(error.message, true)); },220));
  $("#appointment-filter").addEventListener("change", () => loadAppointments().catch(error => showToast(error.message, true)));
  ["appointment-from","appointment-to","appointment-view"].forEach(id=>$("#"+id).addEventListener("change",()=>loadAppointments().catch(error=>showToast(error.message,true))));
  $("#profile-form")?.addEventListener("submit",submitProfile);
  $("#global-search-input").addEventListener("input", event => {
    const query = event.target.value.trim();
    const targetPage = state.page === "dashboard" ? "patients" : state.page;
    if(MODULES[targetPage]&&targetPage!=="settings"&&targetPage!=="reports") {
      state.moduleSearch=query;
      if(state.page!==targetPage) navigate(targetPage);
      else loadModule(targetPage).catch(error=>showToast(error.message,true));
      return;
    }
    if (!["patients", "doctors", "appointments"].includes(targetPage)) return;
    if (targetPage === "patients") {
      state.patientSearch = query;
      $("#patient-search").value = query;
    } else if (targetPage === "doctors") {
      state.doctorSearch = query;
      $("#doctor-search").value = query;
    } else {
      state.appointmentSearch = query;
      $("#appointment-search").value = query;
    }
    if (state.page !== targetPage) navigate(targetPage);
    else loadPageData(targetPage).catch(error => showToast(error.message, true));
  });
}

function start() {
  $("#footer-year").textContent = new Date().getFullYear();
  $("#today-label").textContent = new Intl.DateTimeFormat(undefined, { weekday: "long", month: "long", day: "numeric", year: "numeric" }).format(new Date()).toUpperCase();
  bindEvents();
  api("/api/auth/status").then(status=>{
    if(status.authenticated) { state.user=status.user; return enterWorkspace(); }
    showAuth(status.setup_required);
  }).catch(error=>{
    showAuth(false);
    $("#auth-error").textContent=`Unable to reach the Careflow server: ${error.message}`;
    $("#auth-error").classList.remove("hidden");
  });
}
start();
