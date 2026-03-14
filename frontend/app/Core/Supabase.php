<?php
namespace Frontend\App\Core;

/**
 * Supabase.php - Singleton wrapper for Supabase interactions.
 */
class Supabase
{
    private static ?self $instance = null;
    private string $url;
    private string $key;

    private function __construct()
    {
        $this->url = SUPABASE_URL;
        $this->key = SUPABASE_ANON_KEY;
    }

    public static function getInstance(): self
    {
        if (self::$instance === null) {
            self::$instance = new self();
        }
        return self::$instance;
    }

    /**
     * Get the Supabase URL.
     */
    public function getUrl(): string
    {
        return $this->url;
    }

    /**
     * Get the Supabase Anon Key.
     */
    public function getKey(): string
    {
        return $this->key;
    }
}
