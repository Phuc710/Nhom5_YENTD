import UIController from '../core/UIController.js';

/**
 * ReportsController - OOP Base for Reporting Engine
 */
class ReportsController extends UIController {
    constructor() {
        super();
        this.init();
    }

    async init() {
        console.log('📄 ReportsController Initializing...');
        this.setupListeners();
    }

    setupListeners() {
        const btnExport = document.getElementById('btn-export');
        if (btnExport) {
            btnExport.addEventListener('click', () => this.generateReport());
        }
    }

    generateReport() {
        this.showToast('Đang tổng hợp dữ liệu biên bản...', 'info');

        setTimeout(() => {
            this.showToast('Đã xuất báo cáo định dạng PDF', 'success');
        }, 2000);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.controller = new ReportsController();
});
