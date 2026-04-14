package com.example.cameraai.ui

import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import android.view.MenuItem
import android.view.View
import android.widget.ImageView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.bumptech.glide.Glide
import com.example.cameraai.data.SupabaseClient
import com.example.cameraai.data.model.Violation
import com.example.cameraai.databinding.ActivityDetailBinding
import com.example.cameraai.ui.adapter.ViolationAdapter
import kotlinx.coroutines.launch

class DetailActivity : AppCompatActivity() {

    companion object {
        const val EXTRA_VIOLATION = "extra_violation"
    }

    private lateinit var binding: ActivityDetailBinding
    private var violation: Violation? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityDetailBinding.inflate(layoutInflater)
        setContentView(binding.root)

        setSupportActionBar(binding.toolbar)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        supportActionBar?.title = "Chi tiết vi phạm"

        @Suppress("DEPRECATION")
        violation = intent.getParcelableExtra(EXTRA_VIOLATION)
        if (violation == null) {
            Toast.makeText(this, "Không tải được dữ liệu vi phạm", Toast.LENGTH_SHORT).show()
            finish(); return
        }

        renderViolation(violation!!)
        loadFreshDetail(violation!!.id)
    }

    /** Reload fresh data để lấy payment_status mới nhất */
    private fun loadFreshDetail(id: Int) {
        lifecycleScope.launch {
            try {
                val fresh = SupabaseClient.getViolationDetail(id)
                if (fresh != null) {
                    violation = fresh
                    renderViolation(fresh)
                }
            } catch (_: Exception) { /* giữ dữ liệu cũ */ }
        }
    }

    private fun renderViolation(v: Violation) {
        // ── Ảnh bằng chứng ────────────────────────────────────────
        loadImg(binding.ivFullImage,  v.fullImageUrl)
        loadImg(binding.ivVehicle,    v.croppedVehicleUrl)
        loadImg(binding.ivPlate,      v.croppedPlateUrl)

        if (!v.stopLineSnapshotUrl.isNullOrEmpty()) {
            loadImg(binding.ivStopLine, v.stopLineSnapshotUrl)
            binding.groupStopLine.visibility = View.VISIBLE
        } else {
            binding.groupStopLine.visibility = View.GONE
        }

        // ── Thông tin cơ bản ──────────────────────────────────────
        binding.tvPlate.text          = v.licensePlate ?: "--"
        binding.tvViolationType.text  = v.violationLabel
        binding.tvLightState.text     = v.trafficLightLabel
        binding.tvDateTime.text       = ViolationAdapter.formatDateTime(v.timestamp)
        binding.tvCamera.text         = v.cameraName ?: "--"
        binding.tvLocation.text       = v.location ?: "--"
        binding.tvFine.text           = v.fineDisplay

        // ── Kỹ thuật ─────────────────────────────────────────────
        binding.tvConfidence.text    = if (v.confidence != null) "%.0f%%".format(v.confidence * 100) else "--"
        binding.tvVoteCount.text     = (v.voteCount ?: "--").toString()
        binding.tvVotePercent.text   = if (v.votePercent != null) "%.1f%%".format(v.votePercent) else "--"
        binding.tvQuality.text       = if (v.imageQualityScore != null) "%.1f".format(v.imageQualityScore) else "--"
        binding.tvTrackId.text       = v.trackId?.toString() ?: "--"
        binding.tvProcTime.text      = if (v.processingTimeMs != null) "${v.processingTimeMs}ms" else "--"

        // ── Payment status badge ──────────────────────────────────
        val (badgeText, badgeBg, badgeFg) = when (v.paymentStatus) {
            "paid"    -> Triple("✅ Đã nộp phạt",      Color.parseColor("#ECFDF5"), Color.parseColor("#10B981"))
            "pending" -> Triple("⏳ Đang xác nhận",    Color.parseColor("#FFFBEB"), Color.parseColor("#F59E0B"))
            "failed"  -> Triple("❌ Thất bại",         Color.parseColor("#FEF2F2"), Color.parseColor("#EF4444"))
            else      -> Triple("⚠ Chưa nộp phạt",    Color.parseColor("#FEF2F2"), Color.parseColor("#EF4444"))
        }
        binding.tvPaymentStatus.text = badgeText
        binding.tvPaymentStatus.setBackgroundColor(badgeBg)
        binding.tvPaymentStatus.setTextColor(badgeFg)

        // ── Payment button ────────────────────────────────────────
        if (v.isPaid) {
            binding.btnPay.visibility   = View.GONE
            binding.tvPaidAt.visibility = View.VISIBLE
            binding.tvPaidAt.text       = "✅ Đã nộp lúc: ${ViolationAdapter.formatDateTime(v.paidAt)}"
        } else {
            binding.btnPay.visibility   = View.VISIBLE
            binding.tvPaidAt.visibility = View.GONE
            binding.btnPay.setOnClickListener {
                startActivity(Intent(this, PaymentActivity::class.java).apply {
                    @Suppress("DEPRECATION")
                    putExtra(PaymentActivity.EXTRA_VIOLATION, v)
                })
            }
        }
    }

    private fun loadImg(iv: ImageView, url: String?) {
        if (url.isNullOrEmpty()) { iv.visibility = View.GONE; return }
        iv.visibility = View.VISIBLE
        Glide.with(this).load(url).centerCrop()
            .placeholder(android.R.color.darker_gray)
            .error(android.R.color.holo_red_light)
            .into(iv)
    }

    override fun onResume() {
        super.onResume()
        violation?.id?.let { loadFreshDetail(it) }
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        if (item.itemId == android.R.id.home) { onBackPressedDispatcher.onBackPressed(); return true }
        return super.onOptionsItemSelected(item)
    }
}
