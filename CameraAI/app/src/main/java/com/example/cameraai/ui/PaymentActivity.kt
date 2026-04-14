package com.example.cameraai.ui

import android.content.Intent
import android.os.Bundle
import android.view.MenuItem
import android.view.View
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.bumptech.glide.Glide
import com.example.cameraai.BuildConfig
import com.example.cameraai.data.SePayClient
import com.example.cameraai.data.SePayResult
import com.example.cameraai.data.SupabaseClient
import com.example.cameraai.data.model.Violation
import com.example.cameraai.data.model.ViolationPayment
import com.example.cameraai.databinding.ActivityPaymentBinding
import com.example.cameraai.ui.adapter.ViolationAdapter
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

class PaymentActivity : AppCompatActivity() {

    companion object {
        const val EXTRA_VIOLATION = "extra_violation"
    }

    private lateinit var binding: ActivityPaymentBinding
    private var violation: Violation? = null
    private var payment: ViolationPayment? = null
    private var pollingJob: Job? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityPaymentBinding.inflate(layoutInflater)
        setContentView(binding.root)

        setSupportActionBar(binding.toolbar)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        supportActionBar?.title = "Nộp phạt"

        @Suppress("DEPRECATION")
        violation = intent.getParcelableExtra(EXTRA_VIOLATION)
        if (violation == null) { finish(); return }

        renderViolationInfo(violation!!)
        loadOrCreatePayment(violation!!)
    }

    private fun renderViolationInfo(v: Violation) {
        Glide.with(this)
            .load(v.croppedVehicleUrl ?: v.fullImageUrl)
            .centerCrop()
            .placeholder(android.R.color.darker_gray)
            .into(binding.ivViolationThumb)

        binding.tvPlate.text         = v.licensePlate ?: "--"
        binding.tvViolationType.text = v.violationLabel
        binding.tvViolationTime.text = ViolationAdapter.formatDateTime(v.timestamp)
        binding.tvFineAmount.text    = v.fineDisplay
    }

    private fun loadOrCreatePayment(v: Violation) {
        binding.progressBar.visibility = View.VISIBLE
        lifecycleScope.launch {
            try {
                // 1️⃣ Thử load payment đã có từ DB
                var p = SupabaseClient.getPayment(v.id)

                if (p == null) {
                    val amount  = v.fineAmount ?: 500_000
                    // Tạo mã duy nhất từ violation ID để luôn nhất quán
                    val code    = "VP%06d".format((v.id % 899999) + 100000)
                    val content = "NOPPHAT $code"

                    // Tạo đối tượng ViolationPayment local
                    val newPayment = ViolationPayment(
                        violationId     = v.id,
                        licensePlate    = v.licensePlate ?: "",
                        amount          = amount,
                        status          = "created",
                        paymentCode     = code,
                        transferContent = content,
                        bankAccount     = BuildConfig.BANK_ACCOUNT,
                        bankName        = BuildConfig.BANK_NAME,
                        bankBin         = BuildConfig.BANK_BIN,
                    )

                    // 2️⃣ Cố gắng lưu lên DB (anon key bị RLS block → trả null, không crash)
                    val saved = SupabaseClient.createPayment(newPayment)
                    p = saved ?: newPayment  // Fallback về local object nếu DB block
                }

                payment = p
                renderPayment(p, v)
                startPolling(p)

            } catch (e: Exception) {
                Toast.makeText(
                    this@PaymentActivity,
                    "Lỗi tải thông tin thanh toán: ${e.message}",
                    Toast.LENGTH_LONG
                ).show()
            } finally {
                binding.progressBar.visibility = View.GONE
            }
        }
    }

    private fun renderPayment(p: ViolationPayment, v: Violation) {
        binding.tvPaymentCode.text     = "Mã: ${p.paymentCode}"
        binding.tvTransferContent.text = "Nội dung: ${p.transferContent}"
        binding.tvAmount.text          = "%,d VNĐ".format(p.amount).replace(',', '.')
        binding.tvBankInfo.text        = "${p.bankName} · ${p.bankAccount}"

        updatePaymentStatus(p.status)

        // QR Image từ VietQR CDN (không cần backend)
        val qrUrl = p.vietqrImageUrl ?: p.buildVietQRUrl()
        Glide.with(this)
            .load(qrUrl)
            .placeholder(android.R.color.white)
            .error(android.R.color.holo_red_light)
            .into(binding.ivQrCode)

        binding.btnConfirm.setOnClickListener { manualCheck(p) }
    }

    /** Polling mỗi 5s kiểm tra SePay — tối đa 10 phút */
    private fun startPolling(p: ViolationPayment) {
        pollingJob?.cancel()
        // Chỉ poll nếu SEPAY_TOKEN đã được cấu hình
        if (BuildConfig.SEPAY_TOKEN == "your_sepay_access_token_here") {
            binding.tvPollingStatus.text = "⚠ SePay chưa cấu hình — nhấn \"Xác nhận\" sau khi chuyển khoản"
            return
        }
        pollingJob = lifecycleScope.launch {
            var attempts = 0
            val maxAttempts = 120 // 10 phút tối đa
            while (isActive && attempts < maxAttempts && payment?.status != "paid") {
                delay(5_000)
                checkPayment(p, auto = true)
                attempts++
            }
        }
    }

    /** Kiểm tra SePay webhook */
    private fun checkPayment(p: ViolationPayment, auto: Boolean = false) {
        lifecycleScope.launch {
            if (!auto) {
                binding.btnConfirm.isEnabled = false
                binding.tvPollingStatus.text = "Đang kiểm tra..."
            }
            try {
                val result = SePayClient.checkPayment(
                    paymentCode = p.paymentCode,
                    amount      = p.amount,
                )
                when (result) {
                    is SePayResult.Paid -> {
                        updatePaymentStatus("paid")
                        pollingJob?.cancel()

                        val intent = Intent(this@PaymentActivity, SuccessActivity::class.java).apply {
                            @Suppress("DEPRECATION")
                            putExtra(SuccessActivity.EXTRA_VIOLATION, violation)
                            putExtra(SuccessActivity.EXTRA_TRANSACTION_ID, result.transactionId)
                            putExtra(SuccessActivity.EXTRA_AMOUNT, p.amount)
                        }
                        startActivity(intent)
                        finish()
                    }
                    is SePayResult.NotFound -> {
                        if (!auto) binding.tvPollingStatus.text =
                            "Chưa tìm thấy giao dịch. Vui lòng chuyển khoản theo thông tin trên."
                    }
                    is SePayResult.Error -> {
                        if (!auto) binding.tvPollingStatus.text = "Lỗi kiểm tra: ${result.message}"
                    }
                }
            } catch (e: Exception) {
                if (!auto) binding.tvPollingStatus.text = "Lỗi: ${e.message}"
            } finally {
                if (!auto) binding.btnConfirm.isEnabled = true
            }
        }
    }

    private fun manualCheck(p: ViolationPayment) = checkPayment(p, auto = false)

    private fun updatePaymentStatus(status: String) {
        val (text, color) = when (status) {
            "paid"    -> "✅ Đã thanh toán" to 0xFF00C853.toInt()
            "pending" -> "⏳ Đang xác nhận..." to 0xFFFF6F00.toInt()
            "expired" -> "❌ Đã hết hạn" to 0xFFD32F2F.toInt()
            "created" -> "📱 Quét mã QR để thanh toán" to 0xFF1565C0.toInt()
            else      -> "⏳ Chờ thanh toán" to 0xFF1565C0.toInt()
        }
        binding.tvPaymentStatusResult.text = text
        binding.tvPaymentStatusResult.setTextColor(color)

        val sePayConfigured = BuildConfig.SEPAY_TOKEN != "your_sepay_access_token_here"
        binding.tvPollingStatus.text = when {
            status == "paid"       -> ""
            sePayConfigured        -> "🔄 Tự động kiểm tra mỗi 5 giây..."
            else                   -> "⚠ Nhấn \"Xác nhận\" sau khi đã chuyển khoản"
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        pollingJob?.cancel()
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        if (item.itemId == android.R.id.home) {
            onBackPressedDispatcher.onBackPressed()
            return true
        }
        return super.onOptionsItemSelected(item)
    }
}
