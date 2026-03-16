/**
 * ApiBase - Chuẩn OOP cho việc xử lý HTTP Requests
 */
class ApiBase {
    constructor(baseUrl = '') {
        this.baseUrl = baseUrl.replace(/\/$/, '');
    }

    /**
     * @param {string} path 
     * @param {object} options 
     */
    async fetch(path, options = {}) {
        try {
            const response = await fetch(`${this.baseUrl}${path}`, {
                ...options,
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    ...(options.headers || {})
                }
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || `HTTP Error ${response.status}`);
            }

            return data;
        } catch (error) {
            throw error;
        }
    }

    get(path, options = {}) {
        return this.fetch(path, { ...options, method: 'GET' });
    }

    post(path, body, options = {}) {
        return this.fetch(path, { ...options, method: 'POST', body: JSON.stringify(body) });
    }

    put(path, body, options = {}) {
        return this.fetch(path, { ...options, method: 'PUT', body: JSON.stringify(body) });
    }

    delete(path, options = {}) {
        return this.fetch(path, { ...options, method: 'DELETE' });
    }
}

export default ApiBase;
