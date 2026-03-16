<?php
namespace Frontend\App\Core;

class Router
{
    private array $routes = [];

    public function add(string $pattern, callable|string $handler): void
    {
        $this->routes[$pattern] = $handler;
    }

    public function dispatch(): void
    {
        $uri = parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH);
        // Clean URL: strip .php extension if present
        if (str_ends_with($uri, '.php')) {
            $uri = substr($uri, 0, -4);
        }
        $uri = trim($uri, '/');

        foreach ($this->routes as $pattern => $handler) {
            $pattern = trim($pattern, '/');
            $regex = preg_replace('/\{([a-zA-Z0-9_]+)\}/', '(?P<$1>[^/]+)', $pattern);
            $regex = '#^' . $regex . '$#';

            if (preg_match($regex, $uri, $matches)) {
                $params = array_filter($matches, 'is_string', ARRAY_FILTER_USE_KEY);

                if (is_callable($handler)) {
                    call_user_func_array($handler, $params);
                    return;
                }

                if (is_string($handler)) {
                    $this->renderView($handler, $params);
                    return;
                }
            }
        }

        // Default: 404
        http_response_code(404);
        echo "404 - Page Not Found";
    }

    private function renderView(string $viewPath, array $params = []): void
    {
        extract($params);
        $path = __DIR__ . '/../../views/' . $viewPath . '.php';
        if (file_exists($path)) {
            require_once $path;
        } else {
            echo "View not found: $viewPath";
        }
    }
}
