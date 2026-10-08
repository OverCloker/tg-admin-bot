package com.codex.tgbotcontrol;

import android.Manifest;
import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.media.MediaRecorder;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.SystemClock;
import android.util.Base64;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.view.WindowManager;
import android.view.inputmethod.InputMethodManager;
import android.webkit.WebChromeClient;
import android.webkit.JavascriptInterface;
import android.webkit.PermissionRequest;
import android.webkit.ValueCallback;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;
import android.window.OnBackInvokedCallback;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;

public class MainActivity extends Activity {
    private static final String DEFAULT_URL = "https://app.otvet04ka.com/";
    private static final String LEGACY_DEFAULT_URL = "http://192.168.1.207:8000/";
    private long lastExitBackAt;
    private OnBackInvokedCallback backInvokedCallback;
    private static final int FILE_CHOOSER_REQUEST = 1001;
    private static final int AUDIO_PERMISSION_REQUEST = 1002;

    private SharedPreferences prefs;
    private FrameLayout root;
    private WebView webView;
    private ProgressBar progress;
    private LinearLayout settingsPanel;
    private EditText urlInput;
    private ValueCallback<Uri[]> filePathCallback;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        Window window = getWindow();
        window.addFlags(WindowManager.LayoutParams.FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS);
        window.clearFlags(WindowManager.LayoutParams.FLAG_TRANSLUCENT_STATUS);
        window.clearFlags(WindowManager.LayoutParams.FLAG_TRANSLUCENT_NAVIGATION);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            window.setDecorFitsSystemWindows(false);
        } else {
            window.getDecorView().setSystemUiVisibility(
                    View.SYSTEM_UI_FLAG_LAYOUT_STABLE | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
            );
        }
        window.setStatusBarColor(Color.rgb(246, 248, 251));
        window.setNavigationBarColor(Color.rgb(246, 248, 251));
        prefs = getSharedPreferences("panel_settings", Context.MODE_PRIVATE);
        buildUi();
        if (Build.VERSION.SDK_INT >= 33) {
            backInvokedCallback = this::handleAppBack;
            getOnBackInvokedDispatcher().registerOnBackInvokedCallback(0, backInvokedCallback);
        }
        requestAudioPermissionIfNeeded();
        loadSavedUrl();
    }

    @SuppressLint("SetJavaScriptEnabled")
    private void buildUi() {
        root = new FrameLayout(this);
        root.setBackgroundColor(Color.rgb(246, 248, 251));
        root.setOnApplyWindowInsetsListener((view, insets) -> {
            int top = insets.getSystemWindowInsetTop();
            int bottom = insets.getSystemWindowInsetBottom();
            view.setPadding(0, top, 0, bottom);
            return insets;
        });
        setContentView(root);

        webView = new WebView(this);
        webView.setLayoutParams(new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT
        ));
        webView.getSettings().setJavaScriptEnabled(true);
        webView.getSettings().setDomStorageEnabled(true);
        webView.getSettings().setDatabaseEnabled(true);
        webView.getSettings().setLoadWithOverviewMode(true);
        webView.getSettings().setUseWideViewPort(true);
        webView.getSettings().setBuiltInZoomControls(false);
        webView.getSettings().setDisplayZoomControls(false);
        webView.getSettings().setDefaultTextEncodingName("utf-8");
        webView.getSettings().setCacheMode(WebSettings.LOAD_DEFAULT);
        webView.addJavascriptInterface(new VoiceBridge(), "AndroidVoice");
        webView.addJavascriptInterface(new AppBridge(), "AndroidApp");
        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                return false;
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                progress.setVisibility(View.GONE);
            }
        });
        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onProgressChanged(WebView view, int newProgress) {
                progress.setVisibility(newProgress < 100 ? View.VISIBLE : View.GONE);
                progress.setProgress(newProgress);
            }

            @Override
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (filePathCallback != null) {
                    filePathCallback.onReceiveValue(null);
                }
                filePathCallback = callback;
                try {
                    startActivityForResult(params.createIntent(), FILE_CHOOSER_REQUEST);
                } catch (Exception error) {
                    filePathCallback = null;
                    return false;
                }
                return true;
            }

            @Override
            public void onPermissionRequest(PermissionRequest request) {
                if (Build.VERSION.SDK_INT < Build.VERSION_CODES.LOLLIPOP) {
                    return;
                }
                for (String resource : request.getResources()) {
                    if (PermissionRequest.RESOURCE_AUDIO_CAPTURE.equals(resource) && hasAudioPermission()) {
                        request.grant(new String[]{PermissionRequest.RESOURCE_AUDIO_CAPTURE});
                        return;
                    }
                }
                request.deny();
                requestAudioPermissionIfNeeded();
            }
        });
        root.addView(webView);

        progress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progress.setMax(100);
        progress.setVisibility(View.GONE);
        FrameLayout.LayoutParams progressParams = new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                8,
                Gravity.TOP
        );
        root.addView(progress, progressParams);

        Button settingsButton = new Button(this);
        settingsButton.setText("Адрес");
        settingsButton.setOnClickListener(v -> settingsPanel.setVisibility(View.VISIBLE));
        FrameLayout.LayoutParams settingsButtonParams = new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT,
                ViewGroup.LayoutParams.WRAP_CONTENT,
                Gravity.BOTTOM | Gravity.RIGHT
        );
        settingsButtonParams.rightMargin = 18;
        settingsButtonParams.bottomMargin = 18;
        root.addView(settingsButton, settingsButtonParams);

        settingsPanel = new LinearLayout(this);
        settingsPanel.setOrientation(LinearLayout.VERTICAL);
        settingsPanel.setBackgroundColor(Color.WHITE);
        settingsPanel.setElevation(16f);
        settingsPanel.setVisibility(View.GONE);
        settingsPanel.setPadding(28, 28, 28, 28);
        FrameLayout.LayoutParams panelParams = new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT,
                Gravity.TOP
        );

        TextView title = new TextView(this);
        title.setText("Адрес панели");
        title.setTextSize(20f);
        title.setTextColor(Color.rgb(23, 32, 51));
        settingsPanel.addView(title);

        TextView hint = new TextView(this);
        hint.setText("Панель: https://app.otvet04ka.com/\nЛокальный адрес вводи полностью: http://IP_ПК:8000/");
        hint.setTextColor(Color.rgb(102, 112, 133));
        hint.setPadding(0, 8, 0, 12);
        settingsPanel.addView(hint);

        urlInput = new EditText(this);
        urlInput.setSingleLine(true);
        urlInput.setHint(DEFAULT_URL);
        urlInput.setText(savedPanelUrl());
        settingsPanel.addView(urlInput);

        LinearLayout buttons = new LinearLayout(this);
        buttons.setOrientation(LinearLayout.HORIZONTAL);
        buttons.setGravity(Gravity.RIGHT);
        buttons.setPadding(0, 16, 0, 0);

        Button openButton = new Button(this);
        openButton.setText("Открыть");
        openButton.setOnClickListener(v -> openTypedUrl());
        buttons.addView(openButton);

        Button closeButton = new Button(this);
        closeButton.setText("Закрыть");
        closeButton.setOnClickListener(v -> settingsPanel.setVisibility(View.GONE));
        buttons.addView(closeButton);

        settingsPanel.addView(buttons);
        Button outages = new Button(this);
        outages.setText("Отключения света и виджет");
        outages.setOnClickListener(v -> startActivity(new Intent(this, PowerActivity.class)));
        settingsPanel.addView(outages);
        root.addView(settingsPanel, panelParams);
    }

    private void loadSavedUrl() {
        String url = normalizeUrl(savedPanelUrl());
        urlInput.setText(url);
        webView.loadUrl(url);
    }

    private String savedPanelUrl() {
        String saved = prefs.getString("panel_url", DEFAULT_URL);
        if (LEGACY_DEFAULT_URL.equals(saved)) {
            prefs.edit().putString("panel_url", DEFAULT_URL).apply();
            return DEFAULT_URL;
        }
        return saved;
    }

    private void openTypedUrl() {
        String url = normalizeUrl(urlInput.getText().toString());
        prefs.edit().putString("panel_url", url).commit();
        urlInput.setText(url);
        settingsPanel.setVisibility(View.GONE);
        hideKeyboard();
        webView.loadUrl(url);
    }

    private String normalizeUrl(String raw) {
        String trimmed = raw == null ? "" : raw.trim();
        if (trimmed.isEmpty()) return DEFAULT_URL;
        String withScheme = trimmed.startsWith("http://") || trimmed.startsWith("https://")
                ? trimmed
                : "https://" + trimmed;
        return withScheme.endsWith("/") ? withScheme : withScheme + "/";
    }

    private void hideKeyboard() {
        InputMethodManager imm = (InputMethodManager) getSystemService(Context.INPUT_METHOD_SERVICE);
        if (imm != null) {
            imm.hideSoftInputFromWindow(urlInput.getWindowToken(), 0);
        }
    }

    private class AppBridge {
        @JavascriptInterface
        public void openOutages() {
            runOnUiThread(() -> startActivity(new Intent(MainActivity.this, PowerActivity.class)));
        }

        @JavascriptInterface
        public void setThemeBars(String theme) {
            runOnUiThread(() -> {
                int color;
                boolean lightIcons;
                if ("oled".equals(theme)) {
                    color = Color.BLACK;
                    lightIcons = true;
                } else if ("dark".equals(theme)) {
                    color = Color.rgb(17, 24, 39);
                    lightIcons = true;
                } else if ("glass".equals(theme)) {
                    color = Color.rgb(5, 11, 19);
                    lightIcons = true;
                } else if ("expressive".equals(theme)) {
                    color = Color.rgb(17, 20, 35);
                    lightIcons = true;
                } else if ("warm".equals(theme)) {
                    color = Color.rgb(251, 248, 243);
                    lightIcons = false;
                } else if ("classic".equals(theme)) {
                    color = Color.rgb(0, 128, 128);
                    lightIcons = true;
                } else {
                    color = Color.rgb(246, 248, 251);
                    lightIcons = false;
                }
                Window window = getWindow();
                root.setBackgroundColor(color);
                webView.setBackgroundColor(color);
                window.getDecorView().setBackgroundColor(color);
                window.setStatusBarColor(color);
                window.setNavigationBarColor(color);
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                    window.setStatusBarContrastEnforced(false);
                    window.setNavigationBarContrastEnforced(false);
                }
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                    WindowInsetsController controller = window.getInsetsController();
                    if (controller != null) {
                        int appearance = lightIcons ? 0 : WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS;
                        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && !lightIcons) {
                            appearance |= WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS;
                        }
                        controller.setSystemBarsAppearance(
                                appearance,
                                WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS
                                        | WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS
                        );
                    }
                }
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                    int flags = View.SYSTEM_UI_FLAG_LAYOUT_STABLE | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN;
                    if (!lightIcons) {
                        flags |= View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR;
                    }
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && !lightIcons) {
                        flags |= View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR;
                    }
                    window.getDecorView().setSystemUiVisibility(flags);
                }
            });
        }
    }

    private class VoiceBridge {
        private MediaRecorder recorder;
        private File outputFile;
        private String fileName = "voice.m4a";
        private String mimeType = "audio/mp4";

        @JavascriptInterface
        public boolean startRecord() {
            if (!hasAudioPermission()) {
                runOnUiThread(() -> requestAudioPermissionIfNeeded());
                return false;
            }
            stopQuietly();
            try {
                boolean opus = Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q;
                fileName = opus ? "voice.ogg" : "voice.m4a";
                mimeType = opus ? "audio/ogg" : "audio/mp4";
                outputFile = new File(getCacheDir(), fileName);
                recorder = new MediaRecorder();
                recorder.setAudioSource(MediaRecorder.AudioSource.MIC);
                if (opus) {
                    recorder.setOutputFormat(MediaRecorder.OutputFormat.OGG);
                    recorder.setAudioEncoder(MediaRecorder.AudioEncoder.OPUS);
                    recorder.setAudioEncodingBitRate(32000);
                    recorder.setAudioSamplingRate(48000);
                } else {
                    recorder.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4);
                    recorder.setAudioEncoder(MediaRecorder.AudioEncoder.AAC);
                    recorder.setAudioEncodingBitRate(96000);
                    recorder.setAudioSamplingRate(44100);
                }
                recorder.setOutputFile(outputFile.getAbsolutePath());
                recorder.prepare();
                recorder.start();
                return true;
            } catch (Exception error) {
                stopQuietly();
                return false;
            }
        }

        @JavascriptInterface
        public String stopRecord() {
            if (recorder == null || outputFile == null) {
                return "";
            }
            try {
                recorder.stop();
                recorder.release();
                recorder = null;
                return Base64.encodeToString(readFile(outputFile), Base64.NO_WRAP);
            } catch (Exception error) {
                return "";
            } finally {
                recorder = null;
                if (outputFile != null) {
                    outputFile.delete();
                    outputFile = null;
                }
            }
        }

        @JavascriptInterface
        public String getFileName() {
            return fileName;
        }

        @JavascriptInterface
        public String getMimeType() {
            return mimeType;
        }

        private void stopQuietly() {
            if (recorder != null) {
                try {
                    recorder.stop();
                } catch (Exception ignored) {
                }
                recorder.release();
                recorder = null;
            }
        }

        private byte[] readFile(File file) throws Exception {
            ByteArrayOutputStream output = new ByteArrayOutputStream();
            FileInputStream input = new FileInputStream(file);
            try {
                byte[] buffer = new byte[8192];
                int read;
                while ((read = input.read(buffer)) != -1) {
                    output.write(buffer, 0, read);
                }
                return output.toByteArray();
            } finally {
                input.close();
            }
        }
    }

    private boolean hasAudioPermission() {
        return Build.VERSION.SDK_INT < Build.VERSION_CODES.M
                || checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED;
    }

    private void requestAudioPermissionIfNeeded() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && !hasAudioPermission()) {
            requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, AUDIO_PERMISSION_REQUEST);
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        if (requestCode == FILE_CHOOSER_REQUEST && filePathCallback != null) {
            Uri[] results = WebChromeClient.FileChooserParams.parseResult(resultCode, data);
            filePathCallback.onReceiveValue(results);
            filePathCallback = null;
            return;
        }
        super.onActivityResult(requestCode, resultCode, data);
    }

    @Override
    public void onBackPressed() {
        handleAppBack();
    }

    private void handleAppBack() {
        if (settingsPanel.getVisibility() == View.VISIBLE) {
            settingsPanel.setVisibility(View.GONE);
            lastExitBackAt = 0;
        } else {
            webView.evaluateJavascript("Boolean(window.handleAndroidBack && window.handleAndroidBack())", result -> {
                if ("true".equals(result)) { lastExitBackAt = 0; return; }
                if (webView.canGoBack()) { lastExitBackAt = 0; webView.goBack(); return; }
                long now = SystemClock.elapsedRealtime();
                if (now - lastExitBackAt < 2000) finish();
                else { lastExitBackAt = now; Toast.makeText(this, "Нажмите Назад ещё раз, чтобы выйти", Toast.LENGTH_SHORT).show(); }
            });
        }
    }

    @Override
    protected void onDestroy() {
        if (Build.VERSION.SDK_INT >= 33 && backInvokedCallback != null)
            getOnBackInvokedDispatcher().unregisterOnBackInvokedCallback(backInvokedCallback);
        webView.destroy();
        super.onDestroy();
    }
}
