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

            binding.tvPlate.text         = v.licensePlate ?: "--"
            binding.tvViolationType.text = v.violationLabel
            binding.tvDateTime.text      = formatDateTime(v.timestamp)
            binding.tvLocation.text      = buildString {
                v.cameraName?.let { append(it) }
                v.location?.let { append("  ·  $it") }
            }.ifEmpty { "Không có thông tin" }

            val conf = if (v.confidence != null) "OCR: %.0f%%".format(v.confidence * 100) else ""
            binding.tvConfidence.text = conf

            // Payment badge with background
            val (text, fg, bg) = when (v.paymentStatus) {
                "paid"    -> Triple("✅ Đã nộp",       Color.parseColor("#10B981"), Color.parseColor("#ECFDF5"))
                "pending" -> Triple("⏳ Đang xác nhận", Color.parseColor("#F59E0B"), Color.parseColor("#FFFBEB"))
                "failed"  -> Triple("❌ Thất bại",     Color.parseColor("#EF4444"), Color.parseColor("#FEF2F2"))
                else      -> Triple("⚠ Chưa nộp",     Color.parseColor("#EF4444"), Color.parseColor("#FEF2F2"))
            }
            binding.tvPaymentStatus.text = text
            binding.tvPaymentStatus.setTextColor(fg)
            binding.tvPaymentStatus.setBackgroundColor(bg)

            binding.tvFine.text = v.fineDisplay

            // Thumbnail
            val url = v.croppedVehicleUrl ?: v.fullImageUrl
            if (!url.isNullOrEmpty()) {
                binding.ivThumbnail.visibility = View.VISIBLE
                Glide.with(binding.ivThumbnail)
                    .load(url).centerCrop()
                    .placeholder(android.R.color.darker_gray)
                    .into(binding.ivThumbnail)
            } else {
                binding.ivThumbnail.visibility = View.GONE
            }
        }
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int) =
        VH(ItemViolationBinding.inflate(LayoutInflater.from(parent.context), parent, false))

    override fun onBindViewHolder(holder: VH, position: Int) = holder.bind(getItem(position))

    companion object {
        private val DIFF = object : DiffUtil.ItemCallback<Violation>() {
            override fun areItemsTheSame(a: Violation, b: Violation) = a.id == b.id
            override fun areContentsTheSame(a: Violation, b: Violation) = a == b
        }

        fun formatDateTime(timestamp: String?): String {
            if (timestamp == null) return "--"
            return try {
                val inFmt  = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.getDefault()).also {
                    it.timeZone = TimeZone.getTimeZone("UTC")
                }
                val outFmt = SimpleDateFormat("HH:mm · dd/MM/yyyy", Locale.getDefault()).also {
                    it.timeZone = TimeZone.getTimeZone("Asia/Ho_Chi_Minh")
                }
                val dt = inFmt.parse(timestamp.take(19)) ?: return timestamp
                outFmt.format(dt)
            } catch (_: Exception) { timestamp }
        }
    }
}
