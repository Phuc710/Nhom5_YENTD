package com.example.tracuuvipham;

import android.os.Bundle;
import android.widget.ImageButton;
import android.widget.TextView;
import androidx.appcompat.app.AppCompatActivity;

public class ViolationDetailActivity extends AppCompatActivity {

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_violation_detail);

        // 1. Ánh xạ các thành phần dựa trên ID bạn đã đặt trong XML
        ImageButton btnBack = findViewById(R.id.btnBackDetail);
        TextView tvPlate = findViewById(R.id.tvDetailPlate);
        TextView tvTime = findViewById(R.id.tvDetailTime);
        TextView tvAddress = findViewById(R.id.tvDetailAddress);

        // 2. Nhận dữ liệu truyền từ ResultActivity sang
        String plate = getIntent().getStringExtra("PLATE_DETAIL");

        // Cập nhật giao diện nếu có dữ liệu truyền vào
        if (plate != null && !plate.isEmpty()) {
            tvPlate.setText("Biển số: " + plate.toUpperCase());
        }

        // 3. Xử lý nút quay lại
        btnBack.setOnClickListener(v -> {
            finish(); // Đóng trang 3 để về lại trang 2
        });
    }
}