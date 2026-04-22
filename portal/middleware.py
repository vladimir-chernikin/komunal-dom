"""
Middleware для защиты Django Admin и контроля доступа

АВТОР: Claude Sonnet
ДАТА: 2026-04-02
НАЗНАЧЕНИЕ:
1. Защита Django Admin - только для superuser
2. Добавление company_id и department_id в request для авторизованных пользователей
"""

from django.shortcuts import redirect
from django.urls import reverse
from django.http import HttpResponseForbidden
from portal.mixins import get_user_scope


GLOBAL_DARK_THEME_HEAD = r"""
<script id="global-dark-theme-boot">
(function () {
    try {
        var savedTheme = localStorage.getItem('theme');
        if (savedTheme !== 'light') {
            document.documentElement.setAttribute('data-theme', 'dark');
        }
    } catch (error) {}
})();
</script>
<style id="global-dark-theme-css">
    :root {
        --kd-night-bg: #0f1419;
        --kd-night-bg-2: #141b22;
        --kd-night-surface: #202a33;
        --kd-night-surface-2: #24313b;
        --kd-night-surface-glass: rgba(37, 48, 58, 0.86);
        --kd-night-muted: #2c3944;
        --kd-night-text: #d7e1e8;
        --kd-night-text-muted: #a8b7c2;
        --kd-night-text-soft: #c2ced7;
        --kd-night-field: #18222b;
        --kd-night-field-border: rgba(184, 199, 210, 0.20);
        --kd-night-border: rgba(148, 163, 184, 0.24);
        --kd-night-border-strong: rgba(180, 194, 208, 0.34);
        --kd-night-accent: #34d399;
        --kd-night-accent-2: #38bdf8;
        --kd-night-accent-soft: rgba(52, 211, 153, 0.12);
        --kd-night-accent-border: rgba(52, 211, 153, 0.32);
        --kd-night-shadow: 0 16px 40px rgba(0, 0, 0, 0.32);
        --kd-night-shadow-strong: 0 24px 60px rgba(0, 0, 0, 0.45);
        --kd-night-hero: linear-gradient(180deg, #0c1624 0%, #142536 52%, #163326 100%);
        --kd-night-hero-overlay: radial-gradient(circle at 28% 20%, rgba(52, 211, 153, 0.16), transparent 32%),
                                  linear-gradient(180deg, rgba(7, 12, 18, 0.12), rgba(7, 12, 18, 0.42));
    }

    html[data-theme="dark"] {
        color-scheme: dark;
        --bg-primary: var(--kd-night-bg);
        --bg-secondary: var(--kd-night-bg-2);
        --bg-card: var(--kd-night-surface);
        --surface-primary: var(--kd-night-surface);
        --surface-secondary: var(--kd-night-surface-2);
        --surface-elevated: var(--kd-night-surface-glass);
        --surface-muted: var(--kd-night-muted);
        --text-primary: var(--kd-night-text);
        --text-secondary: var(--kd-night-text-muted);
        --text-soft: var(--kd-night-text-soft);
        --border-color: var(--kd-night-border);
        --border-strong: var(--kd-night-border-strong);
        --navbar-bg: #111820;
        --navbar-text: var(--kd-night-text);
        --footer-bg: var(--kd-night-bg);
        --accent-color: var(--kd-night-accent);
        --accent-soft: var(--kd-night-accent-soft);
        --accent-border: var(--kd-night-accent-border);
        --hero-text: #f2f7fb;
        --hero-text-muted: #cfdae4;
        --hero-bg: var(--kd-night-hero);
        --hero-overlay: var(--kd-night-hero-overlay);
    }

    html:not([data-theme="dark"]) .aerial-hero {
        position: relative;
    }

    html:not([data-theme="dark"]) .aerial-hero::before {
        content: '';
        position: absolute;
        top: clamp(54px, 9vw, 108px);
        right: clamp(28px, 9vw, 128px);
        z-index: 1;
        width: clamp(58px, 8vw, 96px);
        aspect-ratio: 1;
        border-radius: 50%;
        pointer-events: none;
        background:
            radial-gradient(circle at 34% 30%, rgba(255, 255, 255, 0.92) 0 9%, transparent 10%),
            linear-gradient(135deg, rgba(255, 255, 255, 0.52) 0 24%, transparent 25%),
            conic-gradient(from -42deg,
                #fff1a4 0deg 44deg,
                #ffc84b 44deg 92deg,
                #f39a3c 92deg 138deg,
                #ffd967 138deg 184deg,
                #fff4b8 184deg 226deg,
                #ffbd42 226deg 276deg,
                #f58b32 276deg 318deg,
                #ffe082 318deg 360deg);
        border: 1px solid rgba(180, 103, 34, 0.24);
        box-shadow:
            inset 12px -14px 20px rgba(180, 103, 34, 0.22),
            inset -10px 9px 16px rgba(255, 255, 255, 0.55),
            0 0 22px rgba(255, 198, 72, 0.34),
            0 16px 28px rgba(24, 32, 45, 0.15);
        opacity: 0.95;
    }

    html:not([data-theme="dark"]) .aerial-hero::after {
        content: '';
        position: absolute;
        top: clamp(18px, 4vw, 52px);
        right: clamp(4px, 4vw, 72px);
        z-index: 0;
        width: clamp(140px, 16vw, 220px);
        aspect-ratio: 1;
        border-radius: 50%;
        pointer-events: none;
        background:
            radial-gradient(circle,
                rgba(255, 238, 170, 0.34) 0 24%,
                rgba(255, 201, 86, 0.18) 25% 46%,
                rgba(16, 185, 129, 0.07) 47% 62%,
                rgba(255, 255, 255, 0) 68%);
        filter: blur(2px);
        opacity: 0.86;
    }

    html[data-theme="dark"] body,
    html[data-theme="dark"] main {
        background: var(--kd-night-bg);
        color: var(--kd-night-text);
    }

    html[data-theme="dark"] .navbar,
    html[data-theme="dark"] .navbar-custom {
        background: #111820 !important;
        border-color: var(--kd-night-border) !important;
        color: var(--kd-night-text);
        box-shadow: 0 1px 0 rgba(255, 255, 255, 0.04), 0 12px 32px rgba(0, 0, 0, 0.18);
    }

    html[data-theme="dark"] .navbar a,
    html[data-theme="dark"] .navbar .nav-link,
    html[data-theme="dark"] .navbar-brand,
    html[data-theme="dark"] .navbar-user-name {
        color: var(--kd-night-text) !important;
    }

    html[data-theme="dark"] .aerial-hero {
        position: relative;
        background: var(--kd-night-hero) !important;
        color: #f2f7fb;
    }

    html[data-theme="dark"] .aerial-hero::before {
        content: '';
        position: absolute;
        top: clamp(54px, 9vw, 108px);
        right: clamp(28px, 9vw, 128px);
        z-index: 1;
        width: clamp(58px, 8vw, 96px);
        aspect-ratio: 1;
        border-radius: 50%;
        pointer-events: none;
        background:
            radial-gradient(circle at 38% 36%, rgba(255, 255, 255, 0.98) 0 10%, transparent 11%),
            radial-gradient(circle at 66% 64%, rgba(255, 255, 255, 0.55) 0 5%, transparent 6%),
            radial-gradient(circle at 50% 50%, #f8fafc 0 58%, #dbeafe 74%, rgba(191, 219, 254, 0.12) 75%);
        box-shadow: 0 0 28px rgba(191, 219, 254, 0.72), 0 0 72px rgba(147, 197, 253, 0.34);
        opacity: 0.92;
    }

    html[data-theme="dark"] .aerial-hero::after {
        content: '';
        position: absolute;
        inset: 0;
        z-index: 1;
        pointer-events: none;
        background: var(--kd-night-hero-overlay);
    }

    html[data-theme="dark"] .city-3d-background {
        z-index: 0;
        opacity: 0.56;
        filter: brightness(0.56) saturate(0.78) contrast(1.08);
    }

    html[data-theme="dark"] .aerial-content,
    html[data-theme="dark"] .management-shell,
    html[data-theme="dark"] .container.aerial-content {
        position: relative;
        z-index: 2;
        color: #f2f7fb;
    }

    html[data-theme="dark"] h1,
    html[data-theme="dark"] h2,
    html[data-theme="dark"] h3,
    html[data-theme="dark"] h4,
    html[data-theme="dark"] h5,
    html[data-theme="dark"] h6,
    html[data-theme="dark"] .page-title h1,
    html[data-theme="dark"] .aerial-hero h1,
    html[data-theme="dark"] .aerial-hero h2,
    html[data-theme="dark"] .tile-title,
    html[data-theme="dark"] .section-title,
    html[data-theme="dark"] .section-head h2,
    html[data-theme="dark"] .table-container h5,
    html[data-theme="dark"] .stat-value,
    html[data-theme="dark"] .stat-card h2,
    html[data-theme="dark"] .stat-bubble-number,
    html[data-theme="dark"] .card-title {
        color: var(--kd-night-text) !important;
    }

    html[data-theme="dark"] .aerial-hero h1,
    html[data-theme="dark"] .aerial-hero h2,
    html[data-theme="dark"] .page-title h1 {
        text-shadow: 0 2px 18px rgba(0, 0, 0, 0.45);
    }

    html[data-theme="dark"] p,
    html[data-theme="dark"] .subtitle,
    html[data-theme="dark"] .company-title,
    html[data-theme="dark"] .tile-description,
    html[data-theme="dark"] .stat-caption,
    html[data-theme="dark"] .stat-card h5,
    html[data-theme="dark"] .stat-bubble-label,
    html[data-theme="dark"] .text-muted,
    html[data-theme="dark"] .small,
    html[data-theme="dark"] .form-text,
    html[data-theme="dark"] .user-name {
        color: var(--kd-night-text-muted) !important;
    }

    html[data-theme="dark"] a:not(.btn):not(.dropdown-item):not(.navbar-brand):not(.nav-link) {
        color: #86efac;
    }

    html[data-theme="dark"] .breadcrumb,
    html[data-theme="dark"] .breadcrumb-item,
    html[data-theme="dark"] .breadcrumb-item.active {
        color: var(--kd-night-text-muted) !important;
    }

    html[data-theme="dark"] .breadcrumb,
    html[data-theme="dark"] .crumb-card {
        background: rgba(21, 30, 38, 0.76) !important;
        border: 1px solid var(--kd-night-border);
        box-shadow: var(--kd-night-shadow);
    }

    html[data-theme="dark"] .aerial-tile,
    html[data-theme="dark"] .form-container,
    html[data-theme="dark"] .content-container,
    html[data-theme="dark"] .surface-card,
    html[data-theme="dark"] .crumb-card,
    html[data-theme="dark"] .user-card,
    html[data-theme="dark"] .stat-card,
    html[data-theme="dark"] .stat-bubble,
    html[data-theme="dark"] .table-container,
    html[data-theme="dark"] .main-card,
    html[data-theme="dark"] .card,
    html[data-theme="dark"] .modal-content,
    html[data-theme="dark"] .list-group-item,
    html[data-theme="dark"] .department-tree-list,
    html[data-theme="dark"] .department-tree-row,
    html[data-theme="dark"] .work-order-card,
    html[data-theme="dark"] .request-card,
    html[data-theme="dark"] .resident-card,
    html[data-theme="dark"] .executor-card,
    html[data-theme="dark"] .filter-card,
    html[data-theme="dark"] .info-card,
    html[data-theme="dark"] .dashboard-card,
    html[data-theme="dark"] .chat-container,
    html[data-theme="dark"] .message-card {
        background: var(--kd-night-surface-glass) !important;
        border-color: var(--kd-night-border) !important;
        color: var(--kd-night-text) !important;
        box-shadow: var(--kd-night-shadow) !important;
    }

    html[data-theme="dark"] .aerial-tile:hover,
    html[data-theme="dark"] .surface-card:hover,
    html[data-theme="dark"] .work-order-card:hover,
    html[data-theme="dark"] .request-card:hover {
        border-color: var(--kd-night-accent-border) !important;
        box-shadow: var(--kd-night-shadow-strong) !important;
    }

    html[data-theme="dark"] .stat-box {
        background: rgba(52, 211, 153, 0.10) !important;
        border: 1px solid rgba(52, 211, 153, 0.24) !important;
        box-shadow: 0 12px 28px rgba(0, 0, 0, 0.18);
    }

    html[data-theme="dark"] .stat-box .stat-value,
    html[data-theme="dark"] .stat-value {
        color: var(--kd-night-accent) !important;
    }

    html[data-theme="dark"] .stat-box .stat-label,
    html[data-theme="dark"] .stat-label {
        color: var(--kd-night-text-muted) !important;
    }

    html[data-theme="dark"] .request-card {
        background: rgba(32, 42, 51, 0.88) !important;
        border-color: rgba(148, 163, 184, 0.22) !important;
    }

    html[data-theme="dark"] .request-number {
        color: #dce6ed !important;
    }

    html[data-theme="dark"] .request-date,
    html[data-theme="dark"] .request-description,
    html[data-theme="dark"] .service-tag,
    html[data-theme="dark"] .empty-state {
        color: #aebcc7 !important;
    }

    html[data-theme="dark"] .request-footer {
        border-top-color: rgba(148, 163, 184, 0.22) !important;
    }

    html[data-theme="dark"] .request-footer small,
    html[data-theme="dark"] .request-footer small[style] {
        color: var(--kd-night-accent) !important;
    }

    html[data-theme="dark"] .resolution-note {
        background: rgba(52, 211, 153, 0.11) !important;
        border: 1px solid rgba(52, 211, 153, 0.24) !important;
        color: #c8d8d0 !important;
    }

    html[data-theme="dark"] .empty-state i {
        color: rgba(168, 183, 194, 0.46) !important;
    }

    html[data-theme="dark"] .aerial-tile::before {
        background: linear-gradient(90deg, #34d399, #22c55e) !important;
    }

    html[data-theme="dark"] .tile-icon-wrapper,
    html[data-theme="dark"] .stat-icon,
    html[data-theme="dark"] .department-toggle {
        background: linear-gradient(135deg, rgba(52, 211, 153, 0.18), rgba(14, 165, 233, 0.12)) !important;
        border-color: var(--kd-night-accent-border) !important;
        color: var(--kd-night-accent) !important;
    }

    html[data-theme="dark"] .tile-icon,
    html[data-theme="dark"] .stat-icon.primary,
    html[data-theme="dark"] .stat-icon.warning,
    html[data-theme="dark"] .department-title a,
    html[data-theme="dark"] .department-title strong {
        color: var(--kd-night-accent) !important;
    }

    html[data-theme="dark"] .tile-badge,
    html[data-theme="dark"] .status-chip,
    html[data-theme="dark"] .chip,
    html[data-theme="dark"] .department-badge,
    html[data-theme="dark"] .badge.bg-light,
    html[data-theme="dark"] .badge.text-dark {
        background: var(--kd-night-accent-soft) !important;
        border: 1px solid var(--kd-night-accent-border) !important;
        color: var(--kd-night-accent) !important;
    }

    html[data-theme="dark"] .status-badge {
        border: 1px solid transparent;
        box-shadow: none;
    }

    html[data-theme="dark"] .status-new {
        background: rgba(148, 163, 184, 0.16) !important;
        border-color: rgba(148, 163, 184, 0.28) !important;
        color: #c8d2dc !important;
    }

    html[data-theme="dark"] .status-in_work {
        background: rgba(14, 165, 233, 0.15) !important;
        border-color: rgba(56, 189, 248, 0.30) !important;
        color: #b9e5f7 !important;
    }

    html[data-theme="dark"] .status-done {
        background: rgba(34, 197, 94, 0.15) !important;
        border-color: rgba(74, 222, 128, 0.30) !important;
        color: #bdeecb !important;
    }

    html[data-theme="dark"] .status-emergency {
        background: rgba(239, 68, 68, 0.15) !important;
        border-color: rgba(248, 113, 113, 0.34) !important;
        color: #f3b4b4 !important;
    }

    html[data-theme="dark"] .card-header,
    html[data-theme="dark"] .modal-header,
    html[data-theme="dark"] .modal-footer {
        background: var(--kd-night-surface-2) !important;
        border-color: var(--kd-night-border) !important;
        color: var(--kd-night-text) !important;
    }

    html[data-theme="dark"] .table {
        --bs-table-bg: transparent;
        --bs-table-color: var(--kd-night-text);
        --bs-table-border-color: var(--kd-night-border);
        --bs-table-hover-bg: rgba(52, 211, 153, 0.08);
        color: var(--kd-night-text) !important;
        border-color: var(--kd-night-border) !important;
    }

    html[data-theme="dark"] .table thead th,
    html[data-theme="dark"] .table th {
        background: var(--kd-night-surface-2) !important;
        border-color: var(--kd-night-border) !important;
        color: var(--kd-night-text-soft) !important;
    }

    html[data-theme="dark"] .table td,
    html[data-theme="dark"] .table tbody tr,
    html[data-theme="dark"] .department-tree-row {
        border-color: var(--kd-night-border) !important;
        color: var(--kd-night-text) !important;
    }

    html[data-theme="dark"] .table-hover tbody tr:hover,
    html[data-theme="dark"] .department-tree-row:hover {
        background: linear-gradient(90deg, rgba(52, 211, 153, 0.14), rgba(52, 211, 153, 0.06)) !important;
        box-shadow: inset 3px 0 0 rgba(52, 211, 153, 0.72);
    }

    html[data-theme="dark"] .table-hover tbody tr:hover td {
        color: #e3edf3 !important;
    }

    html[data-theme="dark"] .form-control,
    html[data-theme="dark"] .form-select,
    html[data-theme="dark"] textarea,
    html[data-theme="dark"] input[type="text"],
    html[data-theme="dark"] input[type="search"],
    html[data-theme="dark"] input[type="email"],
    html[data-theme="dark"] input[type="password"],
    html[data-theme="dark"] input[type="number"],
    html[data-theme="dark"] input[type="date"],
    html[data-theme="dark"] input[type="datetime-local"],
    html[data-theme="dark"] select {
        background-color: var(--kd-night-field) !important;
        border-color: var(--kd-night-field-border) !important;
        color: var(--kd-night-text-soft) !important;
    }

    html[data-theme="dark"] .form-control::placeholder,
    html[data-theme="dark"] textarea::placeholder,
    html[data-theme="dark"] input::placeholder {
        color: rgba(194, 206, 215, 0.54) !important;
    }

    html[data-theme="dark"] .form-control:focus,
    html[data-theme="dark"] .form-select:focus,
    html[data-theme="dark"] textarea:focus,
    html[data-theme="dark"] input:focus,
    html[data-theme="dark"] select:focus {
        border-color: var(--kd-night-accent) !important;
        box-shadow: 0 0 0 0.2rem rgba(52, 211, 153, 0.16) !important;
    }

    html[data-theme="dark"] .form-label,
    html[data-theme="dark"] label {
        color: var(--kd-night-text-soft) !important;
    }

    html[data-theme="dark"] .form-check-input {
        background-color: var(--kd-night-field) !important;
        border-color: var(--kd-night-field-border) !important;
    }

    html[data-theme="dark"] .form-check-input:checked {
        background-color: var(--kd-night-accent) !important;
        border-color: var(--kd-night-accent) !important;
    }

    html[data-theme="dark"] .object-search-results {
        background: var(--kd-night-surface) !important;
        border-color: var(--kd-night-border) !important;
        box-shadow: var(--kd-night-shadow-strong) !important;
    }

    html[data-theme="dark"] .object-search-item {
        border-color: var(--kd-night-border) !important;
        color: var(--kd-night-text-soft) !important;
    }

    html[data-theme="dark"] .object-search-item:hover,
    html[data-theme="dark"] .object-search-item:focus {
        background: rgba(52, 211, 153, 0.10) !important;
    }

    html[data-theme="dark"] .object-search-meta {
        color: var(--kd-night-text-muted) !important;
    }

    html[data-theme="dark"] .dropdown-menu {
        background: var(--kd-night-surface) !important;
        border-color: var(--kd-night-border) !important;
    }

    html[data-theme="dark"] .dropdown-item {
        color: var(--kd-night-text) !important;
    }

    html[data-theme="dark"] .dropdown-item:hover,
    html[data-theme="dark"] .dropdown-item:focus {
        background: var(--kd-night-muted) !important;
        color: var(--kd-night-text) !important;
    }

    html[data-theme="dark"] .alert {
        border-width: 1px !important;
        border-radius: 12px;
        box-shadow: 0 12px 30px rgba(0, 0, 0, 0.20);
    }

    html[data-theme="dark"] .alert-warning {
        background: rgba(245, 158, 11, 0.13) !important;
        border-color: rgba(251, 191, 36, 0.30) !important;
        color: #f8d68c !important;
    }

    html[data-theme="dark"] .alert-danger,
    html[data-theme="dark"] .alert-error {
        background: rgba(239, 68, 68, 0.13) !important;
        border-color: rgba(248, 113, 113, 0.32) !important;
        color: #f3b4b4 !important;
    }

    html[data-theme="dark"] .alert-success {
        background: rgba(34, 197, 94, 0.13) !important;
        border-color: rgba(74, 222, 128, 0.30) !important;
        color: #bdeecb !important;
    }

    html[data-theme="dark"] .alert-info {
        background: rgba(14, 165, 233, 0.13) !important;
        border-color: rgba(56, 189, 248, 0.30) !important;
        color: #b8e4f6 !important;
    }

    html[data-theme="dark"] .text-danger,
    html[data-theme="dark"] .invalid-feedback,
    html[data-theme="dark"] .errorlist {
        color: #f1a9a9 !important;
    }

    html[data-theme="dark"] .is-invalid,
    html[data-theme="dark"] .form-control.is-invalid,
    html[data-theme="dark"] .form-select.is-invalid {
        border-color: rgba(248, 113, 113, 0.46) !important;
        box-shadow: 0 0 0 0.18rem rgba(239, 68, 68, 0.12) !important;
    }

    html[data-theme="dark"] .is-valid,
    html[data-theme="dark"] .form-control.is-valid,
    html[data-theme="dark"] .form-select.is-valid {
        border-color: rgba(74, 222, 128, 0.42) !important;
        box-shadow: 0 0 0 0.18rem rgba(34, 197, 94, 0.10) !important;
    }

    html[data-theme="dark"] .btn-outline-secondary,
    html[data-theme="dark"] .btn-outline-light {
        border-color: rgba(238, 244, 248, 0.42) !important;
        color: var(--kd-night-text) !important;
    }

    html[data-theme="dark"] .btn-outline-secondary:hover,
    html[data-theme="dark"] .btn-outline-light:hover {
        background: rgba(238, 244, 248, 0.12) !important;
        color: var(--kd-night-text) !important;
    }

    html[data-theme="dark"] .btn-primary,
    html[data-theme="dark"] .btn-success {
        background: #059669 !important;
        border-color: #059669 !important;
        color: #f8fafc !important;
    }

    html[data-theme="dark"] .bg-white,
    html[data-theme="dark"] .bg-light,
    html[data-theme="dark"] .footer-custom {
        background: var(--kd-night-surface) !important;
        color: var(--kd-night-text) !important;
        border-color: var(--kd-night-border) !important;
    }

    .theme-floating-toggle {
        position: fixed;
        right: 18px;
        bottom: 18px;
        z-index: 2147483000;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 46px;
        height: 46px;
        border-radius: 999px;
        border: 1px solid rgba(15, 23, 42, 0.16);
        background: rgba(250, 252, 253, 0.94);
        color: #0f172a;
        box-shadow: 0 12px 30px rgba(15, 23, 42, 0.18);
        backdrop-filter: blur(12px);
        cursor: pointer;
        padding: 0;
        line-height: 1;
        transition: transform 0.2s ease, border-color 0.2s ease, background 0.2s ease, box-shadow 0.2s ease;
    }

    .theme-floating-toggle:hover,
    .theme-floating-toggle:focus-visible {
        transform: translateY(-2px);
        border-color: rgba(52, 211, 153, 0.46);
        box-shadow: 0 16px 34px rgba(15, 23, 42, 0.22);
        outline: none;
    }

    html[data-theme="dark"] .theme-floating-toggle {
        background: rgba(17, 24, 32, 0.84);
        border-color: var(--kd-night-border);
        color: var(--kd-night-text);
        box-shadow: var(--kd-night-shadow);
    }

    html[data-theme="dark"] .theme-floating-toggle:hover,
    html[data-theme="dark"] .theme-floating-toggle:focus-visible {
        border-color: var(--kd-night-accent-border);
        box-shadow: var(--kd-night-shadow-strong);
    }

    .theme-floating-toggle-svg {
        display: block;
        width: 23px;
        height: 23px;
    }

    .theme-floating-toggle .theme-icon-sun {
        display: none;
    }

    .theme-floating-toggle .theme-icon-moon {
        display: block;
    }

    html[data-theme="dark"] .theme-floating-toggle .theme-icon-sun {
        display: block;
    }

    html[data-theme="dark"] .theme-floating-toggle .theme-icon-moon {
        display: none;
    }

    .theme-legacy-toggle-hidden {
        display: none !important;
    }
</style>
"""


GLOBAL_DARK_THEME_BODY = r"""
<script id="global-dark-theme-controls">
(function () {
    function getTheme() {
        try {
            return localStorage.getItem('theme') === 'light' ? 'light' : 'dark';
        } catch (error) {
            return document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
        }
    }

    function setTheme(theme) {
        var isDark = theme === 'dark';
        if (isDark) {
            document.documentElement.setAttribute('data-theme', 'dark');
        } else {
            document.documentElement.removeAttribute('data-theme');
        }
        try {
            localStorage.setItem('theme', isDark ? 'dark' : 'light');
        } catch (error) {}
        updateThemeControls();
    }

    function getToggleIconMarkup() {
        return [
            '<svg class="theme-floating-toggle-svg" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false">',
            '<path class="theme-icon-moon" d="M20.25 15.1A8.25 8.25 0 0 1 8.9 3.75 8.25 8.25 0 1 0 20.25 15.1Z" fill="currentColor"/>',
            '<g class="theme-icon-sun" stroke="currentColor" stroke-width="1.8" stroke-linecap="round">',
            '<circle cx="12" cy="12" r="4.2" fill="currentColor" stroke="none"/>',
            '<path d="M12 2.75v2.1M12 19.15v2.1M4.85 4.85l1.48 1.48M17.67 17.67l1.48 1.48M2.75 12h2.1M19.15 12h2.1M4.85 19.15l1.48-1.48M17.67 6.33l1.48-1.48"/>',
            '</g>',
            '</svg>'
        ].join('');
    }

    function updateIcon(icon, isDark) {
        if (!icon) {
            return;
        }
        if (icon.classList.contains('bi') || icon.className.indexOf('bi-') !== -1) {
            icon.classList.toggle('bi-sun', isDark);
            icon.classList.toggle('bi-moon', !isDark);
        } else if (icon.classList.contains('fas') || icon.className.indexOf('fa-') !== -1) {
            icon.classList.toggle('fa-sun', isDark);
            icon.classList.toggle('fa-moon', !isDark);
        }
    }

    function updateThemeControls() {
        var isDark = document.documentElement.getAttribute('data-theme') === 'dark';
        var icon = document.getElementById('themeIcon');
        updateIcon(icon, isDark);
        document.querySelectorAll('[data-global-theme-toggle]').forEach(function (button) {
            button.setAttribute('aria-label', isDark ? 'Переключить на светлую тему' : 'Переключить на темную тему');
            button.setAttribute('title', isDark ? 'Светлая тема' : 'Темная тема');
        });
    }

    window.toggleTheme = function () {
        setTheme(getTheme() === 'dark' ? 'light' : 'dark');
    };

    function hideLegacyToggles() {
        document.querySelectorAll('#themeToggle').forEach(function (button) {
            button.classList.add('theme-legacy-toggle-hidden');
            button.setAttribute('aria-hidden', 'true');
            button.setAttribute('tabindex', '-1');
            button.onclick = function (event) {
                event.preventDefault();
                window.toggleTheme();
            };
        });
    }

    function ensureFloatingToggle() {
        var button = document.getElementById('globalThemeToggle');
        if (!button) {
            button = document.createElement('button');
            button.type = 'button';
            button.id = 'globalThemeToggle';
            button.className = 'theme-floating-toggle';
            button.setAttribute('data-global-theme-toggle', '1');
            button.innerHTML = getToggleIconMarkup();
            button.addEventListener('click', function (event) {
                event.preventDefault();
                window.toggleTheme();
            });
            document.body.appendChild(button);
        }
        return button;
    }

    document.addEventListener('DOMContentLoaded', function () {
        hideLegacyToggles();
        ensureFloatingToggle();
        updateThemeControls();
    });
})();
</script>
"""


class DarkThemeInjectionMiddleware:
    """Injects the shared dark theme into non-admin HTML pages."""

    excluded_prefixes = (
        '/admin/',
        '/static/',
        '/media/',
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not self._should_inject(request, response):
            return response

        try:
            html = response.content.decode(response.charset or 'utf-8')
        except (AttributeError, UnicodeDecodeError):
            return response

        if 'id="global-dark-theme-css"' in html:
            return response

        if '</head>' in html:
            html = html.replace('</head>', f'{GLOBAL_DARK_THEME_HEAD}\n</head>', 1)
        else:
            return response

        if '</body>' in html:
            html = html.replace('</body>', f'{GLOBAL_DARK_THEME_BODY}\n</body>', 1)

        response.content = html.encode(response.charset or 'utf-8')
        if response.has_header('Content-Length'):
            response['Content-Length'] = str(len(response.content))
        return response

    def _should_inject(self, request, response):
        if any(request.path.startswith(prefix) for prefix in self.excluded_prefixes):
            return False
        if getattr(response, 'streaming', False):
            return False
        if response.get('Content-Encoding'):
            return False
        content_type = response.get('Content-Type', '')
        if not content_type.startswith('text/html'):
            return False
        disposition = response.get('Content-Disposition', '')
        return 'attachment' not in disposition.lower()


class DjangoAdminProtectionMiddleware:
    """
    Защита Django Admin - только superuser

    ПРАВИЛА:
    - Если user.is_superuser = true → разрешен доступ к /admin/
    - Если user.is_staff = true но is_superuser = false → redirect на /admin-uk/
    - Если user не авторизован → redirect на /login/

    ИСТОРИЯ:
    - 2026-04-02: Переписан для использования is_superuser вместо UserProfile.role
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Проверяем только путь /admin/
        if not request.path.startswith('/admin/'):
            return self.get_response(request)

        # Проверяем авторизацию
        if request.user.is_authenticated:
            # Проверяем superuser
            if not request.user.is_superuser:
                # Если staff но не superuser - redirect на /admin-uk/
                if request.user.is_staff:
                    return redirect('/admin-uk/')
                # Если не staff - forbidden
                return HttpResponseForbidden(
                    """
                    <html>
                    <head><title>Доступ запрещен</title></head>
                    <body style="font-family: Arial, sans-serif; text-align: center; padding-top: 100px;">
                        <h1>🚫 Доступ запрещен</h1>
                        <p>У вас нет доступа к панели администрирования Django.</p>
                        <p><a href="/">На главную</a></p>
                    </body>
                    </html>
                    """
                )

        # Superuser или неавторизованный - разрешаем (Django сам разберется с login)
        return self.get_response(request)


class CompanyMembershipMiddleware:
    """
    Добавление компании и подразделения в request

    Для авторизованных staff пользователей добавляет:
    - request.user_company_id
    - request.user_department_id
    - request.user_role_code (теперь из UserProfile.job_title)
    - request.user_primary_membership

    ПРИОРИТЕТ чтения:
    1. UserProfile.primary_company и UserProfile.primary_department (новый механизм)
    2. UserCompanyMembership с is_primary=True (fallback для старых данных)
    3. Любая активная UserCompanyMembership (последний fallback)

    РОЛЬ (user_role_code):
    - Определяется через get_role_from_job_title() из UserProfile.job_title
    - Fallback на membership.role_code для обратной совместимости

    ИСПОЛЬЗУЕТСЯ в views для фильтрации по компании.

    ИСТОРИЯ:
    - 2026-04-02: Создан для работы с UserCompanyMembership
    - 2026-04-06: Обновлен для чтения primary из UserProfile с fallback на membership
    - 2026-04-09: Роль теперь определяется из UserProfile.job_title
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Только для авторизованных пользователей
        if request.user.is_authenticated and request.user.is_staff:
            try:
                scope = get_user_scope(request.user)
                primary_membership = scope['primary_membership']
                request.user_company_ids = scope['company_ids']
                request.user_department_ids = scope['department_ids']

                if primary_membership:
                    request.user_company_id = primary_membership.company_id
                    request.user_department_id = primary_membership.department_id
                    request.user_primary_membership = primary_membership
                else:
                    request.user_company_id = None
                    request.user_department_id = None
                    request.user_primary_membership = None

                if request.user.is_superuser:
                    request.user_role_code = 'superuser'
                elif primary_membership:
                    request.user_role_code = primary_membership.role_code
                else:
                    request.user_role_code = None
            except Exception:
                # В случае ошибки (например, при миграциях) - игнорируем
                request.user_company_id = None
                request.user_department_id = None
                request.user_role_code = None
                request.user_primary_membership = None
                request.user_company_ids = []
                request.user_department_ids = []

        return self.get_response(request)
