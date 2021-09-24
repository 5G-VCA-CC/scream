use failure::Error;
use std::env;

extern crate failure;
extern crate gstreamer_video as gstv;
#[macro_use]
extern crate lazy_static;

use crate::gst::glib::Cast;

use crate::gstv::prelude::ElementExt;
use crate::gstv::prelude::GstObjectExt;

extern crate gstreamer as gst;

mod sender_util;

fn main() {
    println!("Hello, world!");

    gst::init().expect("Failed to initialize gst_init");

    let main_loop = glib::MainLoop::new(None, false);
    start(&main_loop).expect("Failed to start");
}

pub fn start(main_loop: &glib::MainLoop) -> Result<(), Error> {
    let pls = env::var("SENDPIPELINE").unwrap();
    println!("Pipeline: {}", pls);
    let pipeline = gst::parse_launch(&pls).unwrap();
    let pipeline = pipeline.downcast::<gst::Pipeline>().unwrap();

    pipeline
        .set_state(gst::State::Playing)
        .expect("Failed to set pipeline to `Playing`");

    let pipeline = pipeline.downcast::<gst::Pipeline>().unwrap();

    let pipeline_clone = pipeline;
    /*  TBD
     * set ecn bits
     */
    sender_util::stats(&pipeline_clone, &Some("screamtx".to_string()));
    sender_util::run_time_bitrate_set(
        &pipeline_clone,
        &Some("screamtx".to_string()),
        &Some("video".to_string()),
    );
    let main_loop_cloned = main_loop.clone();
    let bus = pipeline_clone.bus().unwrap();
    bus.add_watch(move |_, msg| {
        use gst::MessageView;
        // println!("sender: {:?}", msg.view());
        match msg.view() {
            MessageView::Eos(..) => {
                println!("Bus watch  Got eos");
                main_loop_cloned.quit();
            }
            MessageView::Error(err) => {
                println!(
                    "Error from {:?}: {} ({:?})",
                    err.src().map(|s| s.path_string()),
                    err.error(),
                    err.debug()
                );
            }
            _ => (),
        };
        glib::Continue(true)
    })
    .expect("failed to add bus watch");

    main_loop.run();
    pipeline_clone
        .set_state(gst::State::Null)
        .expect("Failed to set pipeline to `Null`");
    println!("Done");
    Ok(())
}