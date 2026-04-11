package com.example.cameraai.ui

import android.annotation.SuppressLint
import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.animation.AlphaAnimation
import android.view.animation.AnimationSet
import android.view.animation.ScaleAnimation
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.example.cameraai.data.SupabaseClient
import com.example.cameraai.databinding.ActivitySplashBinding
import com.example.cameraai.util.Prefs
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

@SuppressLint("CustomSplashScreen")
class SplashActivity : AppCompatActivity() {

    private lateinit var binding: ActivitySplashBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivitySplashBinding.inflate(layoutInflater)
        setContentView(binding.root)

        // Animate logo
        val fadeIn = AlphaAnimation(0f, 1f).apply { duration = 600 }
        val scaleUp = ScaleAnimation(0.7f, 1f, 0.7f, 1f,
            ScaleAnimation.RELATIVE_TO_SELF, 0.5f,
            ScaleAnimation.RELATIVE_TO_SELF, 0.5f).apply { duration = 600 }
        val set = AnimationSet(true).apply {
            addAnimation(fadeIn); addAnimation(scaleUp)
        }
        binding.ivLogo.startAnimation(set)

        lifecycleScope.launch {
            // Step 1 — delay cho animation
            updateStatus("Đang khởi động...", 5)
            delay(600)

            // Step 2 — init Supabase (lazy init)
            updateStatus("Kết nối cơ sở dữ liệu...", 30)
            try {
                SupabaseClient.client  // trigger lazy init
                updateStatus("Kết nối thành công ✓", 60)
            } catch (e: Exception) {
                Log.e("Splash", "Supabase init error: ${e.message}")
                updateStatus("Kết nối thất bại — kiểm tra mạng", 60)
            }
            delay(400)

            // Step 3 — check saved plate
            updateStatus("Kiểm tra phiên đăng nhập...", 85)
            delay(300)

            val savedPlate = Prefs.getSavedPlate(this@SplashActivity)
            val savedNorm  = Prefs.getSavedNorm(this@SplashActivity)

            updateStatus("Hoàn tất!", 100)
            delay(300)

            // Navigate
            if (savedPlate != null && savedNorm != null) {
                // Đã có biển số → thẳng vào Home
                val intent = Intent(this@SplashActivity, HomeActivity::class.java).apply {
                    putExtra(HomeActivity.EXTRA_PLATE, savedPlate)
                    putExtra(HomeActivity.EXTRA_PLATE_NORM, savedNorm)
                }
                startActivity(intent)
            } else {
                // Chưa có biển số → Login
                startActivity(Intent(this@SplashActivity, LoginActivity::class.java))
            }
            finish()
        }
    }

    private fun updateStatus(msg: String, progress: Int) {
        binding.tvStatus.text   = msg
        binding.progressBar.progress = progress
    }
}
