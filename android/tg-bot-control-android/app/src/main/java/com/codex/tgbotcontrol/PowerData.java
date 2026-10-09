package com.codex.tgbotcontrol;

import android.content.Context;
import android.content.SharedPreferences;
import org.json.JSONArray;
import org.json.JSONObject;
import java.net.HttpURLConnection;
import java.net.URI;
import java.net.URL;
import java.net.URLEncoder;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.time.ZonedDateTime;
import java.time.ZoneId;

final class PowerData {
    static final ZoneId KYIV = ZoneId.of("Europe/Kyiv");
    static SharedPreferences prefs(Context c, int id) { return c.getSharedPreferences("power_" + id, Context.MODE_PRIVATE); }
    static String encode(String value) throws Exception { return URLEncoder.encode(value, "UTF-8"); }
    static String server(Context c) {
        String raw = c.getSharedPreferences("panel_settings", 0).getString("panel_url", "https://app.otvet04ka.com/");
        try {
            URI uri = new URI(raw);
            if (("https".equals(uri.getScheme()) || "http".equals(uri.getScheme())) && uri.getHost() != null && uri.getUserInfo() == null)
                return uri.getScheme() + "://" + uri.getRawAuthority();
        } catch (Exception ignored) {}
        return "https://app.otvet04ka.com";
    }
    static JSONObject get(String url) throws Exception {
        HttpURLConnection connection = (HttpURLConnection) new URL(url).openConnection();
        connection.setConnectTimeout(8000); connection.setReadTimeout(15000);
        connection.setInstanceFollowRedirects(false);
        connection.setRequestProperty("Accept", "application/json");
        connection.setRequestProperty("User-Agent", "Mozilla/5.0 (Android) Abstergo/0.4");
        try {
            if (connection.getResponseCode() != 200) throw new Exception("Сервер графиков недоступен (" + connection.getResponseCode() + ")");
            try (InputStream input = connection.getInputStream(); ByteArrayOutputStream output = new ByteArrayOutputStream()) {
                byte[] buffer = new byte[4096]; int n;
                while ((n = input.read(buffer)) != -1) { output.write(buffer, 0, n); if (output.size() > 1000000) throw new Exception("Некорректный ответ сервера"); }
                return new JSONObject(output.toString("UTF-8"));
            }
        } finally { connection.disconnect(); }
    }
    static JSONObject fetch(Context c, int id, boolean tomorrow) throws Exception {
        SharedPreferences p = prefs(c, id);
        String day = ZonedDateTime.now(KYIV).toLocalDate().plusDays(tomorrow ? 1 : 0).toString();
        String group = p.getString("group", "");
        String path = p.getString("path", "");
        JSONObject data = get(p.getString("server", server(c)) + "/power/schedule?location=" + encode(path)
                + "&group=" + encode(group) + "&day=" + day);
        if (!day.equals(data.optString("date")) || !group.equals(data.optString("group"))) throw new Exception("Дата или группа графика не совпадает");
        if(!group.equals(p.getString("group",""))||!path.equals(p.getString("path","")))throw new Exception("Настройки изменились во время загрузки");
        p.edit().putString(tomorrow ? "tomorrow" : "today", data.toString()).apply();
        return data;
    }
    static JSONObject cached(Context c, int id, boolean tomorrow) {
        try { return new JSONObject(prefs(c,id).getString(tomorrow ? "tomorrow" : "today", "{}")); }
        catch (Exception ignored) { return new JSONObject(); }
    }
    static String clock(int minutes) { return String.format(java.util.Locale.ROOT, "%02d:%02d", minutes / 60, minutes % 60); }
    static void markStale(Context c,int id,boolean tomorrow) {
        JSONObject data=cached(c,id,tomorrow);if(data.length()==0)return;
        try {data.put("stale",true);prefs(c,id).edit().putString(tomorrow?"tomorrow":"today",data.toString()).apply();}catch(Exception ignored){}
    }
    static String intervalLabel(String status) { return "on".equals(status) ? "Свет по графику" : "off".equals(status) ? "Отключение" : "Нет точных данных"; }
    static String[] summary(JSONObject data, ZonedDateTime now) {
        if (!now.toLocalDate().toString().equals(data.optString("date")))
            return new String[]{"График не загружен", "Проверьте соединение и обновите", ""};
        if(!data.optBoolean("published"))return new String[]{"Сегодня без графиков", "Источник не опубликовал расписание", ""};
        int minute = now.getHour()*60 + now.getMinute();
        JSONArray slots = data.optJSONArray("intervals");
        if (slots != null) for (int i=0;i<slots.length();i++) {
            JSONObject slot = slots.optJSONObject(i);
            if (slot != null && slot.optInt("start", -1) <= minute && minute < slot.optInt("end", -1)) {
                String state = slot.optString("status");
                return new String[]{"on".equals(state) ? "По графику свет есть" : "off".equals(state) ? "По графику отключён" : "Статус неизвестен",
                        "До " + clock(slot.optInt("end")) + " · время Киева", state};
            }
        }
        return new String[]{"Нет данных на это время", "Обновите график", ""};
    }
}
