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
        int[] all=java.util.Arrays.copyOf(large,large.length+small.length);
        System.arraycopy(small,0,all,large.length,small.length);return all;
    }
    @Override public void onUpdate(Context c, AppWidgetManager manager, int[] ids) {
        for (int id:ids) {
            SharedPreferences p=PowerData.prefs(c,id);
            if (!p.contains("path")) {
                SharedPreferences global=PowerData.prefs(c,0);
                for (String key:new String[]{"path","name","group","server","today","tomorrow"})
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
    static void render(Context c,int id) {
        SharedPreferences p=PowerData.prefs(c,id);
        JSONObject data=PowerData.cached(c,id,false);
        ZonedDateTime now=ZonedDateTime.now(PowerData.KYIV);
        if(!now.toLocalDate().toString().equals(data.optString("date"))) {
            JSONObject tomorrow=PowerData.cached(c,id,true);
            if(now.toLocalDate().toString().equals(tomorrow.optString("date")))data=tomorrow;
        }
        if(!p.getString("group","").equals(data.optString("group"))||!p.getString("path","").equals(data.optString("location")))data=new JSONObject();
        AppWidgetManager manager=AppWidgetManager.getInstance(c);
        android.appwidget.AppWidgetProviderInfo info=manager.getAppWidgetInfo(id);
        boolean compact=info!=null&&info.provider.getClassName().equals(PowerCompactWidget.class.getName());
        RemoteViews view=new RemoteViews(c.getPackageName(),compact?R.layout.power_widget_compact:R.layout.power_widget);
        String name=p.getString("name","Выберите населённый пункт").split(",")[0];
        view.setTextViewText(R.id.power_title,"⚡ " + name + (p.contains("group") ? " · " + p.getString("group","") : ""));
        String[] summary=PowerData.summary(data,now);
        view.setTextViewText(R.id.power_status,summary[0]);view.setTextViewText(R.id.power_next,summary[1]);
        view.setTextColor(R.id.power_status,"on".equals(summary[2])?0xff276747:"off".equals(summary[2])?0xffac4931:0xff66564c);
        if(compact) {
            String event="Нет графика",time="",eventState="";
            JSONArray slots=data.optJSONArray("intervals");int minute=now.getHour()*60+now.getMinute();
            if(now.toLocalDate().toString().equals(data.optString("date"))&&data.optBoolean("published")&&slots!=null) {
                event="До конца дня\nбез смены";
                for(int i=0;i<slots.length();i++) {
                    JSONObject slot=slots.optJSONObject(i);
                    if(slot!=null&&slot.optInt("start",-1)>minute&&!slot.optString("status").equals(summary[2])) {
                        String state=slot.optString("status");
                        event="off".equals(state)?"Отключение":"on".equals(state)?"Включение":"Уточняется";
                        time=PowerData.clock(slot.optInt("start"));eventState=state;break;
                    }
                }
                if(time.isEmpty()) {
                    JSONObject tomorrow=PowerData.cached(c,id,true);JSONArray next=tomorrow.optJSONArray("intervals");
                    if(now.toLocalDate().plusDays(1).toString().equals(tomorrow.optString("date"))&&tomorrow.optBoolean("published")
                            &&p.getString("group","").equals(tomorrow.optString("group"))&&p.getString("path","").equals(tomorrow.optString("location"))&&next!=null) {
                        for(int i=0;i<next.length();i++){JSONObject slot=next.optJSONObject(i);if(slot==null||slot.optString("status").equals(summary[2]))continue;
                            eventState=slot.optString("status");event="off".equals(eventState)?"Отключение":"on".equals(eventState)?"Включение":"Уточняется";
                            time=PowerData.clock(slot.optInt("start"))+"\nзавтра";break;
                        }
                    }
                }
            }
            view.setTextViewText(R.id.power_status,event);view.setTextViewText(R.id.power_next,time);
            view.setTextColor(R.id.power_status,"on".equals(eventState)?0xff276747:"off".equals(eventState)?0xffac4931:0xff66564c);
        } else {
            StringBuilder day=new StringBuilder();JSONArray slots=data.optJSONArray("intervals");
            if(now.toLocalDate().toString().equals(data.optString("date"))&&data.optBoolean("published")&&slots!=null) {
                for(int i=0;i<slots.length();i++) {JSONObject s=slots.optJSONObject(i);if(s==null)continue;
                    day.append("off".equals(s.optString("status"))?"● ":"on".equals(s.optString("status"))?"○ ":"? ")
                       .append(PowerData.clock(s.optInt("start"))).append("–").append(PowerData.clock(s.optInt("end"))).append("  ");
                }
            }
            view.setTextViewText(R.id.power_day,day.length()==0?"График на сегодня пока не опубликован":"Сегодня · оранжевый: отключение · зелёный: свет");
            view.setImageViewBitmap(R.id.power_timeline,timeline(data,now));
        }
        String updated=data.optString("sourceUpdated");
        String saved="";
        try {
            long age=Duration.between(ZonedDateTime.parse(data.getString("fetchedAt")),now).toMinutes();
            if(age>45||data.optBoolean("stale"))saved=" · сохранённые данные";
        }catch(Exception ignored){}
        view.setTextViewText(R.id.power_updated,updated.isEmpty()?"Без Світла · данных пока нет":"Обновлено " + updated + saved);
        Intent open=new Intent(c,PowerActivity.class).putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID,id)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TOP);
        PendingIntent config=PendingIntent.getActivity(c,id,open,PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);
        view.setOnClickPendingIntent(R.id.power_body,config);
        view.setOnClickPendingIntent(R.id.power_refresh,PendingIntent.getBroadcast(c,id,new Intent(c,PowerWidget.class).setAction(REFRESH),PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE));
        AppWidgetManager.getInstance(c).updateAppWidget(id,view);
    }
    private static android.graphics.Bitmap timeline(JSONObject data,ZonedDateTime now) {
        android.graphics.Bitmap bitmap=android.graphics.Bitmap.createBitmap(800,120,android.graphics.Bitmap.Config.ARGB_8888);
        android.graphics.Canvas canvas=new android.graphics.Canvas(bitmap);
        android.graphics.Paint paint=new android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG);
        paint.setColor(0xffddd4c9);canvas.drawRoundRect(12,35,788,83,10,10,paint);
        JSONArray slots=data.optJSONArray("intervals");
        if(now.toLocalDate().toString().equals(data.optString("date"))&&data.optBoolean("published")&&slots!=null) {
            for(int i=0;i<slots.length();i++) {JSONObject s=slots.optJSONObject(i);if(s==null)continue;
                paint.setColor("off".equals(s.optString("status"))?0xffc77648:"on".equals(s.optString("status"))?0xff70a88c:0xffaaa49d);
                canvas.drawRect(12+s.optInt("start")/1440f*776,35,12+s.optInt("end")/1440f*776,83,paint);
            }
            paint.setColor(0xff32291f);paint.setStrokeWidth(3);
            float x=12+(now.getHour()*60+now.getMinute())/1440f*776;canvas.drawLine(x,28,x,90,paint);
        }
        paint.setColor(0xff66564c);paint.setTextSize(23);
        for(int hour=0;hour<=24;hour+=3){float x=12+hour/24f*776;paint.setTextAlign(hour==0?android.graphics.Paint.Align.LEFT:hour==24?android.graphics.Paint.Align.RIGHT:android.graphics.Paint.Align.CENTER);canvas.drawText(String.format(java.util.Locale.ROOT,"%02d",hour),x,112,paint);}
        return bitmap;
    }
}
