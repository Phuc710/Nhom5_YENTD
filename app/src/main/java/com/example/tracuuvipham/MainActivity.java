package com.example.tracuuvipham;

import android.content.Intent;
import android.os.Bundle;
import android.view.View;

import androidx.appcompat.app.AppCompatActivity;

import com.google.android.material.button.MaterialButton;
import com.google.android.material.button.MaterialButtonToggleGroup;
import com.google.android.material.textfield.TextInputEditText;

public class MainActivity extends AppCompatActivity {

    private TextInputEditText edtPlate;
    private MaterialButton btnSearch;
    private MaterialButtonToggleGroup toggleGroup;

    private String vehicleType = "OTO"; // mặc định

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        edtPlate = findViewById(R.id.edtPlate);
        btnSearch = findViewById(R.id.btnSearch);
        toggleGroup = findViewById(R.id.toggleGroup);

        toggleGroup.check(R.id.btnCar);

        toggleGroup.addOnButtonCheckedListener(
                new MaterialButtonToggleGroup.OnButtonCheckedListener() {
                    @Override
                    public void onButtonChecked(MaterialButtonToggleGroup group, int checkedId, boolean isChecked) {
                        if (!isChecked) return;

                        if (checkedId == R.id.btnCar) {
                            vehicleType = "OTO";
                        } else if (checkedId == R.id.btnBike) {
                            vehicleType = "XEMAY";
                        }
                    }
                }
        );

        btnSearch.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {

                String plateNumber = edtPlate.getText().toString().trim().toUpperCase();

                if (plateNumber.isEmpty()) {
                    edtPlate.setError("Vui lòng nhập biển số xe!");
                    edtPlate.requestFocus();
                    return;
                }

                Intent intent = new Intent(MainActivity.this, ResultActivity.class);
                intent.putExtra("KEY_BIEN_SO", plateNumber);
                intent.putExtra("KEY_LOAI_XE", vehicleType);
                startActivity(intent);
            }
        });
    }
}
