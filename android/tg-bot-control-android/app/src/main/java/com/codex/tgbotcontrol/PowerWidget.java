package com.codex.tgbotcontrol;

import android.app.PendingIntent;
import android.app.job.JobInfo;
import android.app.job.JobScheduler;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.widget.RemoteViews;
import org.json.JSONObject;
import org.json.JSONArray;
import java.time.ZonedDateTime;
import java.time.Duration;

public class PowerWidget extends AppWidgetProvider {
    static final int PERIODIC = 421003, IMMEDIATE = 421004;
    static final String REFRESH = "com.codex.tgbotcontrol.POWER_REFRESH";
    static int[] ids(Context c) {
        AppWidgetManager m=AppWidgetManager.getInstance(c);
        int[] large=m.getAppWidgetIds(new ComponentName(c,PowerWidget.class));
        int[] small=m.getAppWidgetIds(new ComponentName(c,PowerCompactWidget.class));
        int[] list=m.getAppWidgetIds(new ComponentName(c,PowerListWidget.class));
        int[] all=java.util.Arrays.copyOf(large,large.length+small.length+list.length);
        System.arraycopy(small,0,all,large.length,small.length);
        System.arraycopy(list,0,all,large.length+small.length,list.length);return all;
    }
    @Override public void onUpdate(Context c, AppWidgetManager manager, int[] ids) {
        for (int id:ids) {
            SharedPreferences p=PowerData.prefs(c,id);
            if (!p.contains("path")) {
                SharedPreferences global=PowerData.prefs(c,0);
                for (String key:new String[]{"path","name","group","server","today","tomorrow","widget_theme","widget_transparency"})
                    if (global.contains(key)) p.edit().putString(key,global.getString(key,"")).apply();
            }
            render(c,id);
        }
        JobScheduler scheduler=(JobScheduler)c.getSystemService(Context.JOB_SCHEDULER_SERVICE);
        scheduler.schedule(new JobInfo.Builder(PERIODIC,new ComponentName(c,PowerJobService.class)).setPeriodic(15*60*1000L).build());
        refresh(c);
    }
    @Override public void onReceive(Context c,Intent intent) {
        super.onReceive(c,intent);
        if (REFRESH.equals(intent.getAction())) { for(int id:ids(c))render(c,id); refresh(c); }
    }
    @Override public void onAppWidgetOptionsChanged(Context c,AppWidgetManager m,int id,Bundle options) { render(c,id); }
    @Override public void onDeleted(Context c,int[] ids) { for(int id:ids)PowerData.prefs(c,id).edit().clear().apply(); }
    @Override public void onDisabled(Context c) {
        if(ids(c).length>0)return;
        JobScheduler s=(JobScheduler)c.getSystemService(Context.JOB_SCHEDULER_SERVICE);s.cancel(PERIODIC);s.cancel(IMMEDIATE);
    }
    static void refresh(Context c) {
        ((JobScheduler)c.getSystemService(Context.JOB_SCHEDULER_SERVICE)).schedule(
                new JobInfo.Builder(IMMEDIATE,new ComponentName(c,PowerJobService.class)).setOverrideDeadline(0).build());
    }
    static void boundary(Context c) {
        ZonedDateTime now=ZonedDateTime.now(PowerData.KYIV);
        long wait=Duration.between(now,now.toLocalDate().plusDays(1).atStartOfDay(PowerData.KYIV)).toMillis();
        int minute=now.getHour()*60+now.getMinute();
        for(int id:ids(c)) {
            JSONObject data=PowerData.cached(c,id,false);
            if(!now.toLocalDate().toString().equals(data.optString("date")))continue;
            JSONArray slots=data.optJSONArray("intervals");
            if(slots!=null)for(int i=0;i<slots.length();i++) {
                JSONObject slot=slots.optJSONObject(i);int end=slot==null?-1:slot.optInt("end",-1);
                if(end>minute)wait=Math.min(wait,(end-minute)*60000L-now.getSecond()*1000L);
            }
        }
        ((JobScheduler)c.getSystemService(Context.JOB_SCHEDULER_SERVICE)).schedule(
                new JobInfo.Builder(IMMEDIATE,new ComponentName(c,PowerJobService.class))
                        .setMinimumLatency(Math.max(1000,wait)).setOverrideDeadline(Math.max(1000,wait)+300000).build());
    }
    static void render(Context c,int id) { AdaptivePowerViews.update(c,id); }
}
