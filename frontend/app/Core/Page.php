<?php
namespace Frontend\App\Core;

class Page
{
    public function __construct(
        public string $title = APP_NAME,
        public string $activePage = 'dashboard',
        public array $extraCss = [],
        public array $extraJs = [],
        public array $appConfig = [],
        public string $section = 'admin',
    ) {
    }

    public function fullTitle(): string
    {
        return $this->title . ' | ' . APP_NAME;
    }

    public function configScript(): string
    {
        $config = array_merge([
            'API_URL' => API_URL,
            'APP_NAME' => APP_NAME,
            'TIMEZONE' => TIMEZONE,
            'SECTION' => $this->section,
        ], $this->appConfig);

        $json = json_encode($config, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
        return "<script>window.APP_CONFIG = {$json};</script>";
    }
}
