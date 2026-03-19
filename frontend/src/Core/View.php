<?php

namespace App\Core;

class View
{
    protected static $templatesPath = __DIR__ . '/../../templates';

    public static function render(string $template, array $data = []): void
    {
        extract($data);

        $templateFile = self::$templatesPath . '/' . $template . '.php';
        if (is_file($templateFile)) {
            require $templateFile;
        } else {
            echo "Template not found: " . htmlspecialchars($template);
        }
    }
}
