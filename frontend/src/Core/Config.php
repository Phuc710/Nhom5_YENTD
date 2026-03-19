<?php

namespace App\Core;

class Config
{
    private static $items = [];
    private static $loaded = [];

    public static function load(string $path): void
    {
        $realPath = realpath($path) ?: $path;
        if (isset(self::$loaded[$realPath])) {
            return;
        }

        if (!is_file($path)) {
            return;
        }

        foreach (file($path, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) as $line) {
            $line = trim($line);
            if ($line === '' || str_starts_with($line, '#') || !str_contains($line, '=')) {
                continue;
            }

            [$key, $value] = explode('=', $line, 2);
            $key = trim($key);
            $value = trim($value);
            $value = trim($value, "\"'");

            if ($key !== '') {
                self::$items[$key] = $value;
            }
        }

        self::$loaded[$realPath] = true;
    }

    public static function get(string $key, $default = null)
    {
        return self::$items[$key] ?? $default;
    }

    public static function getApiBaseUrl(string $defaultApiBaseUrl = ''): string
    {
        $mode = strtolower(trim((string) self::get('FRONTEND_API_MODE', 'direct')));
        if ($mode === 'same_origin') {
            return '';
        }

        $publicApi = trim((string) self::get('PUBLIC_API_URL', ''));
        $apiUrlStr = trim((string) self::get('API_URL', ''));

        $apiUrl = $publicApi !== '' ? $publicApi : ($apiUrlStr !== '' ? $apiUrlStr : $defaultApiBaseUrl);
        return rtrim($apiUrl, '/');
    }

    public static function all(): array
    {
        return self::$items;
    }
}
