package com.example.cameraai.ui

import android.content.Intent
import android.os.Bundle
import android.view.MenuItem
import android.view.View
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

        // Nhận Parcelable từ Intent
        violation = intent.getParcelableExtra(EXTRA_VIOLATION)
        if (violation == null) {
            Toast.makeText(this, "Không tải được dữ liệu vi phạm", Toast.LENGTH_SHORT).show()
            finish(); return
        }

        renderViolation(violation!!)
        loadFreshDetail(violation!!.id)
    }

    /** Load fresh data từ DB để có payment info mới nhất */
    private fun loadFreshDetail(id: Int) {
        lifecycleScope.launch {
            try {
                val fresh = SupabaseClient.getViolationDetail(id)
                if (fresh != null) {
                    violation = fresh
                    renderViolation(fresh)
                }
            } catch (e: Exception) {
                // Giữ dữ liệu cũ nếu load fail
            }
        }
    }

    private fun renderViolation(v: Violation) {
        // ── Ảnh bằng chứng ──────────────────────────────────────────
        loadImage(binding.ivFullImage, v.fullImageUrl)
        loadImage(binding.ivVehicle,  v.croppedVehicleUrl)
        loadImage(binding.ivPlate,    v.croppedPlateUrl)

        // Stop line snapshot (nếu có)
        if (!v.stopLineSnapshotUrl.isNullOrEmpty()) {
            loadImage(binding.ivStopLine, v.stopLineSnapshotUrl)
            binding.groupStopLine.visibility = View.VISIBLE
        } else {
            binding.groupStopLine.visibility = View.GONE
        }

        // ── Thông tin cơ bản ─────────────────────────────────────────
        binding.tvPlate.text         = v.licensePlate ?: "--"
        binding.tvViolationType.text = v.violationLabel
        binding.tvLightState.text    = "Đèn: ${v.trafficLightLabel}"
        binding.tvDateTime.text      = ViolationAdapter.formatDateTime(v.timestamp)
        binding.tvCamera.text        = v.cameraName ?: "--"
        binding.tvLocation.text      = v.location ?: "--"
        binding.tvFine.text          = v.fineDisplay

        // ── Thông tin kỹ thuật ───────────────────────────────────────
        binding.tvConfidence.text    = if (v.confidence != null) "%.0f%%".format(v.confidence * 100) else "--"
        binding.tvTrackId.text       = v.trackId?.toString() ?: "--"
        binding.tvVoteCount.text     = "${v.voteCount ?: "--"} frames"
        binding.tvVotePercent.text   = if (v.votePercent != null) "%.1f%%".format(v.votePercent) else "--"
        binding.tvProcTime.text      = if (v.processingTimeMs != null) "${v.processingTimeMs}ms" else "--"
        binding.tvQuality.text       = if (v.imageQualityScore != null) "%.2f".format(v.imageQualityScore) else "--"

        // ── Trạng thái thanh toán ────────────────────────────────────
        binding.tvPaymentStatus.text = v.paymentStatusLabel
        if (v.isPaid) {
            binding.btnPay.visibility = View.GONE
            binding.tvPaidAt.visibility = View.VISIBLE
            binding.tvPaidAt.text = "✅ Đã nộp lúc: ${ViolationAdapter.formatDateTime(v.paidAt)}"
        } else {
            binding.btnPay.visibility   = View.VISIBLE
            binding.tvPaidAt.visibility = View.GONE
        }

        // ── Button Nộp phạt ──────────────────────────────────────────
        binding.btnPay.setOnClickListener {
            val intent = Intent(this, PaymentActivity::class.java).apply {
                putExtra(PaymentActivity.EXTRA_VIOLATION, v)
            }
            startActivity(intent)
        }
    }

    private fun loadImage(imageView: android.widget.ImageView, url: String?) {
        if (url.isNullOrEmpty()) {
            imageView.visibility = View.GONE
            return
        }
        imageView.visibility = View.VISIBLE
        Glide.with(this).load(url).centerCrop()
            .placeholder(android.R.color.darker_gray)
            .error(android.R.color.holo_red_light)
            .into(imageView)
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        if (item.itemId == android.R.id.home) { onBackPressedDispatcher.onBackPressed(); return true }
        return super.onOptionsItemSelected(item)
    }

    override fun onResume() {
        super.onResume()
        violation?.id?.let { loadFreshDetail(it) }
    }
}
