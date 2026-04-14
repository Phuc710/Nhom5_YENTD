package com.example.cameraai.ui

import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.view.View
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.example.cameraai.data.SupabaseClient
import com.example.cameraai.databinding.ActivityLoginBinding
import com.example.cameraai.util.PlateUtils
import com.example.cameraai.util.Prefs
import kotlinx.coroutines.launch

class LoginActivity : AppCompatActivity() {

    private lateinit var binding: ActivityLoginBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityLoginBinding.inflate(layoutInflater)
        setContentView(binding.root)

        setupUI()
    }

    private fun setupUI() {
        // Auto-uppercase while typing
        binding.etPlate.addTextChangedListener(object : TextWatcher {
            override fun afterTextChanged(s: Editable?) {
                val cur = s.toString()
                val upper = cur.uppercase()
                if (cur != upper) {
                    binding.etPlate.setText(upper)
                    binding.etPlate.setSelection(upper.length)
                }
            }
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
        })

        // Paste from clipboard
        binding.btnPaste.setOnClickListener {
            val clip = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
            val text = clip.primaryClip?.getItemAt(0)?.text?.toString() ?: return@setOnClickListener
            binding.etPlate.setText(text.uppercase().replace(Regex("[^A-Z0-9]"), ""))
        }

        // Search button
        binding.btnSearch.setOnClickListener {
            val raw        = binding.etPlate.text.toString().trim()
            val normalized = PlateUtils.normalize(raw)

            if (!PlateUtils.isValid(raw)) {
                binding.tvError.visibility = View.VISIBLE
                binding.tvError.text = "Biển số không hợp lệ (VD: 79YB23423)"
                return@setOnClickListener
            }

            binding.tvError.visibility = View.GONE
            doSearch(raw, normalized)
        }
    }

    private fun doSearch(plate: String, normalized: String) {
        binding.btnSearch.isEnabled = false
        binding.progressBar.visibility = View.VISIBLE
        binding.tvError.visibility = View.GONE

        lifecycleScope.launch {
            try {
                val exists = SupabaseClient.checkPlateExists(normalized)
                if (exists) {
                    // Lưu biển số
                    Prefs.savePlate(this@LoginActivity, plate, normalized)
                    // Lưu session vào DB (best-effort)
                    val deviceId = Prefs.getDeviceId(this@LoginActivity)
                    SupabaseClient.saveSession(plate, normalized, deviceId)

                    // Navigate to Home
                    val intent = Intent(this@LoginActivity, HomeActivity::class.java).apply {
                        putExtra(HomeActivity.EXTRA_PLATE, plate)
                        putExtra(HomeActivity.EXTRA_PLATE_NORM, normalized)
                    }
                    startActivity(intent)
                    finish()
                } else {
                    binding.tvError.visibility = View.VISIBLE
                    binding.tvError.text = "❌ Không tìm thấy vi phạm nào cho biển số: $plate"
                }
            } catch (e: Exception) {
                binding.tvError.visibility = View.VISIBLE
                binding.tvError.text = "Lỗi kết nối: ${e.message}"
            } finally {
                binding.btnSearch.isEnabled = true
                binding.progressBar.visibility = View.GONE
            }
        }
    }
}
