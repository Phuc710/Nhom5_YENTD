package com.example.tracuuvipham;

import android.content.Intent;
import android.os.Bundle;
import android.widget.ImageButton;
import android.widget.LinearLayout;
import android.widget.TextView;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.content.ContextCompat;

import com.google.android.material.button.MaterialButton;

public class ResultActivity extends AppCompatActivity {

    private TextView tvPoints, tvStatusGPLX;
    private ImageButton btnBack;
    private LinearLayout layoutViolationItem;

    // CHỈ THÊM BIẾN NÀY
    private MaterialButton btnLogout;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_result);

        // 1. Ánh xạ
        tvPoints = findViewById(R.id.tvPoints);
        tvStatusGPLX = findViewById(R.id.tvStatusGPLX);
        btnBack = findViewById(R.id.btnBack);
        layoutViolationItem = findViewById(R.id.layoutViolationItem);

        // CHỈ THÊM DÒNG NÀY
        btnLogout = findViewById(R.id.btnLogout);

        // 2. Quay lại trang chủ
        btnBack.setOnClickListener(v -> finish());

        // 3. Nhận dữ liệu biển số từ trang trước (MainActivity)
        String plate = getIntent().getStringExtra("KEY_BIEN_SO");

        // 4. Logic hiển thị điểm
        if (plate != null) {
            String plateUpper = plate.toUpperCase();
            if (plateUpper.contains("30A") || plateUpper.contains("62G")) {
                tvPoints.setText("10/12");
                tvStatusGPLX.setText("Cảnh báo: Đã bị trừ điểm");
                tvPoints.setTextColor(ContextCompat.getColor(this, android.R.color.holo_red_dark));
            } else {
                tvPoints.setText("12/12");
                tvStatusGPLX.setText("Bằng lái đang có hiệu lực");
                tvPoints.setTextColor(ContextCompat.getColor(this, android.R.color.holo_green_dark));
            }
        }

        // 5. CLICK VÀO Ô VI PHẠM ĐỂ CHUYỂN TRANG 3
        layoutViolationItem.setOnClickListener(v -> {
            Intent intent = new Intent(ResultActivity.this, ViolationDetailActivity.class);
            intent.putExtra("PLATE_DETAIL", plate);
            startActivity(intent);
        });

        // ===== CHỈ THÊM PHẦN XỬ LÝ LOGOUT =====
        btnLogout.setOnClickListener(v -> {
            Intent intent = new Intent(ResultActivity.this, MainActivity.class);

            // Xóa stack để không quay lại trang result nữa
            intent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TASK);

            startActivity(intent);
            finish();
        });
    }
}
