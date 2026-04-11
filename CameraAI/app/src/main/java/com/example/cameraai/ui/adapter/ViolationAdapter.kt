package com.example.cameraai.ui.adapter

import android.graphics.Color
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.ListAdapter
import androidx.recyclerview.widget.RecyclerView
import com.bumptech.glide.Glide
import com.example.cameraai.data.model.Violation
import com.example.cameraai.databinding.ItemViolationBinding
import java.text.SimpleDateFormat
import java.util.*

class ViolationAdapter(
    private val onClick: (Violation) -> Unit
) : ListAdapter<Violation, ViolationAdapter.VH>(DIFF) {

    inner class VH(val binding: ItemViolationBinding) : RecyclerView.ViewHolder(binding.root) {
        fun bind(v: Violation) {
            binding.root.setOnClickListener { onClick(v) }

            // Biển số
            binding.tvPlate.text = v.licensePlate ?: "--"

            // Loại vi phạm
            binding.tvViolationType.text = v.violationLabel

            // Ngày giờ — parse timestamp ISO
            binding.tvDateTime.text = formatDateTime(v.timestamp)

            // Camera / địa điểm
            binding.tvLocation.text = buildString {
                v.cameraName?.let { append(it) }
                v.location?.let { loc -> append(" · $loc") }
            }.ifEmpty { "Không có thông tin" }

            // Payment status badge
            val (badgeText, badgeColor) = when (v.paymentStatus) {
                "paid"    -> "✅ Đã nộp phạt" to Color.parseColor("#00C853")
                "pending" -> "⏳ Đang xác nhận" to Color.parseColor("#FF6F00")
                "failed"  -> "❌ Thất bại" to Color.parseColor("#D32F2F")
                else      -> "⚠ Chưa nộp" to Color.parseColor("#E53935")
            }
            binding.tvPaymentStatus.text = badgeText
            binding.tvPaymentStatus.setTextColor(badgeColor)

            // Số tiền phạt
            binding.tvFine.text = v.fineDisplay

            // Thumbnail ảnh
            val imageUrl = v.croppedVehicleUrl ?: v.fullImageUrl
            if (!imageUrl.isNullOrEmpty()) {
                Glide.with(binding.ivThumbnail)
                    .load(imageUrl)
                    .centerCrop()
                    .placeholder(android.R.color.darker_gray)
                    .into(binding.ivThumbnail)
                binding.ivThumbnail.visibility = View.VISIBLE
            } else {
                binding.ivThumbnail.visibility = View.GONE
            }

            // Confidence
            val conf = if (v.confidence != null) "%.0f%%".format(v.confidence * 100) else "--"
            binding.tvConfidence.text = "OCR: $conf"
        }
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH {
        val binding = ItemViolationBinding.inflate(
            LayoutInflater.from(parent.context), parent, false
        )
        return VH(binding)
    }

    override fun onBindViewHolder(holder: VH, position: Int) = holder.bind(getItem(position))

    companion object {
        private val DIFF = object : DiffUtil.ItemCallback<Violation>() {
            override fun areItemsTheSame(a: Violation, b: Violation) = a.id == b.id
            override fun areContentsTheSame(a: Violation, b: Violation) = a == b
        }

        fun formatDateTime(timestamp: String?): String {
            if (timestamp == null) return "--"
            return try {
                val inFmt  = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.getDefault())
                val outFmt = SimpleDateFormat("HH:mm · dd/MM/yyyy", Locale.getDefault())
                inFmt.timeZone = TimeZone.getTimeZone("UTC")
                outFmt.timeZone = TimeZone.getTimeZone("Asia/Ho_Chi_Minh")
                val dt = inFmt.parse(timestamp.take(19)) ?: return timestamp
                outFmt.format(dt)
            } catch (e: Exception) { timestamp }
        }
    }
}
