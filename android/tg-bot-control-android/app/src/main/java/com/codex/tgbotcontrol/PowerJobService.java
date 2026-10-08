package com.codex.tgbotcontrol;

import android.app.job.JobService;
import android.app.job.JobParameters;
import android.os.Handler;
import android.os.Looper;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class PowerJobService extends JobService {
    private final java.util.concurrent.ConcurrentHashMap<Integer,ExecutorService> workers=new java.util.concurrent.ConcurrentHashMap<>();
    @Override public boolean onStartJob(JobParameters params) {
        ExecutorService worker=Executors.newSingleThreadExecutor();
        ExecutorService previous=workers.put(params.getJobId(),worker);
        if(previous!=null)previous.shutdownNow();
        worker.execute(() -> {
            for(int id:PowerWidget.ids(this)) {
                if(Thread.currentThread().isInterrupted())return;
                if(PowerData.prefs(this,id).contains("path")) {
                    try { PowerData.fetch(this,id,false); } catch(Exception ignored) {PowerData.markStale(this,id,false);}
                    try { PowerData.fetch(this,id,true); } catch(Exception ignored) {PowerData.markStale(this,id,true);}
                }
                PowerWidget.render(this,id);
            }
            new Handler(Looper.getMainLooper()).post(() -> {
                if(!workers.remove(params.getJobId(),worker))return;
                jobFinished(params,false);
                if(PowerWidget.ids(this).length>0)PowerWidget.boundary(this);
                worker.shutdown();
            });
        });
        return true;
    }
    @Override public boolean onStopJob(JobParameters params) { ExecutorService worker=workers.remove(params.getJobId());if(worker!=null)worker.shutdownNow();return PowerWidget.ids(this).length>0; }
    @Override public void onDestroy() { for(ExecutorService worker:workers.values())worker.shutdownNow();workers.clear();super.onDestroy(); }
}
