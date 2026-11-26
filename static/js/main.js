// Sidebar toggle (mobile)
const toggle = document.getElementById('sidebarToggle');
if (toggle) toggle.addEventListener('click', () => document.getElementById('sidebar').classList.toggle('show'));

// Confirm before delete / vacate
document.querySelectorAll('form[data-confirm]').forEach(f => {
  f.addEventListener('submit', e => { if (!confirm(f.dataset.confirm)) e.preventDefault(); });
});

// Auto-fill fee amount from the selected student's room rent
const feeStudent = document.getElementById('feeStudent');
const feeAmount = document.getElementById('feeAmount');
if (feeStudent && feeAmount) {
  feeStudent.addEventListener('change', () => {
    const fee = feeStudent.selectedOptions[0].dataset.fee;
    if (fee) feeAmount.value = fee;
  });
}
