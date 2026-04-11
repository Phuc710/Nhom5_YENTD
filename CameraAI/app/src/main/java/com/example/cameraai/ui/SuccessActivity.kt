package com.example.cameraai.ui

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.view.animation.AlphaAnimation
import android.view.animation.ScaleAnimation
import android.view.animation.AnimationSet
import androidx.appcompat.app.AppCompatActivity
import com.example.cameraai.data.model.Violation
import com.example.cameraai.databinding.ActivitySuccessBinding
import com.example.cameraai.ui.adapter.ViolationAdapter
import java.text.SimpleDateFormat
import java.util.*

class SuccessActivity : AppCompatActivity() {

    companion object {
        const val EXTRA_VIOLATION      = "extra_violation"
        const val EXTRA_TRANSACTION_ID = "extra_transaction_id"
        const val EXTRA_AMOUNT         = "extra_amount"
    }

    private lateinit var binding: ActivitySuccessBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivitySuccessBinding.inflate(layoutInflater)
        setContentView(binding.root)

        val violation     = intent.getParcelableExtra<Violation>(EXTRA_VIOLATION)
        val transactionId = intent.getStringExtra(EXTRA_TRANSACTION_ID) ?: "--"
        val amount        = intent.getIntExtra(EXTRA_AMOUNT, 0)

        // Animate checkmark
        val scaleAnim = AnimationSet(true).apply {
            addAnimation(ScaleAnimation(0f, 1.2f, 0f, 1.2f,
                ScaleAnimation.RELATIVE_TO_SELF, 0.5f,
                ScaleAnimation.RELATIVE_TO_SELF, 0.5f).apply { duration = 400 })
            addAnimation(AlphaAnimation(0f, 1f).apply { duration = 400 })
        }
        binding.ivSuccess.startAnimation(scaleAnim)

        // Info
        binding.tvTitle.text       = "Thanh toán thành công!"
        binding.tvPlate.text       = "Biển số: ${violation?.licensePlate ?: "--"}"
        binding.tvViolationType.text = violation?.violationLabel ?: "--"
        binding.tvAmount.text      = "%,d VNĐ".format(amount).replace(',', '.')
        binding.tvTransactionId.text = "Mã GD: $transactionId"
        binding.tvConfirmedAt.text = "Thời gian: ${
            SimpleDateFormat("HH:mm · dd/MM/yyyy", Locale.getDefault()).format(Date())
        }"

        // Buttons
        binding.btnBackDetail.setOnClickListener {
            finish() // Quay lại DetailActivity
        }

        binding.btnBackHome.setOnClickListener {
            // Clear stack → Home
            val intent = Intent(this, HomeActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP
            }
            startActivity(intent)
            finish()
        }
    }

    // Không cho back stack về PaymentActivity
    override fun onBackPressed() {
        binding.btnBackHome.performClick()
    }
}
