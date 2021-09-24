use std::env;
use std::fs::File;
use std::io::Write;
use std::sync::{Arc, Mutex};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use crate::gstv::prelude::ClockExt;
use crate::gstv::prelude::GstBinExt;
use glib::ObjectExt;

use crate::gstv::prelude::PipelineExt;

use glib::timeout_add;
use glib::Continue;
extern crate gstreamer_video as gstv;

#[derive(Default)]
struct RateInfo {
    rate: u32,
    st: Duration,
    count: u32,
}

pub fn stats(bin: &gst::Pipeline, screamtx_name_opt: &Option<String>) {
    let sender_stats_timer: u32 = env::var("SENDER_STATS_TIMER")
        .ok()
        .and_then(|s| s.parse().ok())
        .unwrap_or(1000);
    println!("SENDER_STATS_TIMER={}", sender_stats_timer);
    if sender_stats_timer == 0 {
        return;
    }
    if screamtx_name_opt.is_none() {
        println!("no scream name");
        return;
    }
    let pipeline_clock = bin.pipeline_clock();

    let sender_stats_file_name: String;

    sender_stats_file_name =
        env::var("SENDER_STATS_FILE_NAME").unwrap_or_else(|_| "sender_scream_stats.csv".into());
    println!("SENDER_STATS_FILE_NAME={}", sender_stats_file_name);
    let mut out: File;
    out = File::create(&sender_stats_file_name).unwrap();

    let scream_name = screamtx_name_opt.as_ref().unwrap();
    let screamtx_e = match bin.by_name(scream_name) {
        Some(v) => v,
        None => {
            println!(" no {}", scream_name);
            return;
        }
    };

    let screamtx_e_clone = screamtx_e.clone();
    let stats_str_header = screamtx_e
        .property("stats-header")
        .expect("Failed to get stats-header")
        .get::<String>()
        .expect("stats");

    writeln!(out, "time-ns, {}", stats_str_header).unwrap();

    let outp_opt: Option<Arc<Mutex<File>>> = Some(Arc::new(Mutex::new(out)));

    timeout_add(
        Duration::from_millis(sender_stats_timer as u64),
        move || {
            let stats_str = screamtx_e_clone
                .property("stats")
                .expect("Failed to get stats")
                .get::<String>()
                .expect("stats");

            let tm = pipeline_clock.time();
            let ns = tm.unwrap().nseconds();
            let out_p = outp_opt.as_ref().unwrap();
            let mut fd = out_p.lock().unwrap();

            writeln!(fd, "{},{}", ns, stats_str).unwrap();
            Continue(true)
        },
    );
}

lazy_static! {
    static ref RATE_INFO_PREV: Mutex<RateInfo> = Mutex::new(RateInfo {
        ..RateInfo::default()
    });
}

pub fn run_time_bitrate_set(
    bin: &gst::Pipeline,
    screamtx_name_opt: &Option<String>,
    encoder_name_opt: &Option<String>,
) {
    if encoder_name_opt.is_none() {
        println!("no encoder_name_opt");
        return;
    }
    println!("{:?} {:?}", encoder_name_opt, screamtx_name_opt);
    let encoder_name = encoder_name_opt.as_ref().unwrap();
    println!("{:?}", encoder_name);
    let video = bin.by_name(encoder_name).expect("Failed to by_name video");

    let video_cloned = video;
    match screamtx_name_opt.as_ref() {
        Some(scream_name) => {
            match bin.by_name(scream_name) {
                Some(scream) => {
                    let scream_cloned = scream.clone();
                    scream.connect("notify::current-max-bitrate", false,  move |_values| {
                        let rate = scream_cloned.property("current-max-bitrate")
                            .expect("Failed to get bitrate").get::<u32>().expect("bitrate");
                        video_cloned
                            .set_property("bitrate", &rate)
                            .expect("Failed to set bitrate");
                        let n = SystemTime::now().duration_since(UNIX_EPOCH).unwrap();

                        let rate_prev;
                        let st_prev;
                        let mut rate_info_prev = RATE_INFO_PREV.lock().unwrap();
                        rate_prev = rate_info_prev.rate;
                        st_prev = rate_info_prev.st;
                        let diff = n.as_secs() - st_prev.as_secs();
                        if diff >= 1 {
                            if rate != rate_prev {
                                    println!("notif: {}.{:06} rate {:05} rate_prev {:05} time_prev {}.{:06} diff {} count {}",
                                             n.as_secs(), n.subsec_micros(), rate, rate_prev, st_prev.as_secs(),
                                             st_prev.subsec_micros(), diff, rate_info_prev.count);
                                    rate_info_prev.rate = rate;
                                    rate_info_prev.st = n;
                                    rate_info_prev.count = 0;
                            }
                        } else {
                                rate_info_prev.count += 1;
                                // println!("count {}", rate_info_prev.count);
                        }
                        None
                    }).unwrap();
                }
                None => println!("no scream signal"),
            }
        }
        None => println!("no scream name"),
    }
}