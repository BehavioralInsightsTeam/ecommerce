define([
        'jquery',
        'underscore',
        'views/coupon_form_view',
        'views/alert_view',
        'models/coupon_model',
        'test/mock_data/categories',
        'test/mock_data/coupons',
        'ecommerce'
    ],
    function ($,
              _,
              CouponFormView,
              AlertView,
              Coupon,
              Mock_Categories,
              Mock_Coupons,
              ecommerce) {
        'use strict';

        describe('coupon form view', function () {
            var view,
                model,
                courseData = Mock_Coupons.courseData;

            /**
              * Helper function to check if a form field is shown.
              */
            function visible(selector) {
                var formGroup = view.$el.find(selector).closest('.form-group');
                if (formGroup.length > 0) {
                    return !formGroup.hasClass('hidden');
                } else {
                    return false;
                }
            }

            beforeEach(function () {
                ecommerce.coupons = {
                    categories: Mock_Categories
                };
                model = new Coupon();
                view = new CouponFormView({ editing: false, model: model }).render();
            });

            describe('seat type dropdown', function () {

                var courseId = 'course-v1:edX+DemoX+Demo_Course',
                    seatType;

                beforeEach(function () {
                    jasmine.clock().install();
                    seatType = view.$el.find('[name=seat_type]');
                    spyOn($, 'ajax').and.callFake(function (options) {
                        options.success(courseData);
                    });
                    view.$el.find('[name=course_id]').val(courseId).trigger('input');
                    // event is debounced, override _.now to trigger immediately
                    spyOn(_, 'now').and.returnValue(Date.now() + 110);
                    jasmine.clock().tick(110);
                });

                afterEach(function () {
                    jasmine.clock().uninstall();
                });

                it('should fill seat type options from course ID', function () {
                    expect($.ajax).toHaveBeenCalled();
                    expect(seatType.children().length).toBe(2);
                    expect(seatType.children()[0].innerHTML).toBe('Verified');
                    expect(seatType.children()[1].innerHTML).toBe('Honor');
                });

                it('should set stock_record_ids from seat type', function () {
                    seatType.children()[0].selected = true;
                    seatType.trigger('change');
                    expect(model.get('stock_record_ids')).toEqual([2]);
                });

                it('changeTotalValue should call updateTotalValue', function () {
                    spyOn(view, 'updateTotalValue');
                    spyOn(view, 'getSeatData');
                    view.changeTotalValue();
                    expect(view.updateTotalValue).toHaveBeenCalled();
                    expect(view.getSeatData).toHaveBeenCalled();
                });

                it('updateTotalValue should calculate the price and update model and form fields', function () {
                    view.$el.find('[name=quantity]').val(5).trigger('input');
                    view.updateTotalValue({price: 100});
                    expect(view.$el.find('input[name=price]').val()).toEqual('500');
                    expect(view.$el.find('input[name=total_value]').val()).toEqual('500');
                    expect(model.get('total_value')).toEqual(500);
                });
            });


            describe('enrollment code', function () {
                beforeEach(function () {
                    view.$el.find('[name=code_type]').val('enrollment').trigger('change');
                });

                it('should show the price field', function () {
                    expect(visible('[name=price]')).toBe(true);
                });

                it('should hide discount and code fields', function () {
                    expect(visible('[name=benefit_value]')).toBe(false);
                    expect(visible('[name=code]')).toBe(false);
                });

                it('should show the quantity field only for single-use vouchers', function () {
                    view.$el.find('[name=voucher_type]').val('Single use').trigger('change');
                    expect(visible('[name=quantity]')).toBe(true);
                    view.$el.find('[name=voucher_type]').val('Multi-use').trigger('change');
                    expect(visible('[name=quantity]')).toBe(false);
                    view.$el.find('[name=voucher_type]').val('Once per customer').trigger('change');
                    expect(visible('[name=quantity]')).toBe(false);
                });
            });

            describe('discount', function () {
                beforeEach(function () {
                    view.$el.find('[name=code_type]').val('Discount code').trigger('change');
                });

                it('should show the discount field', function () {
                    expect(visible('[name=benefit_value]')).toBe(true);
                });

                it('should indicate the benefit type', function () {
                    view.$el.find('[name=code_type]').val('enrollment').trigger('change');
                    expect(view.$el.find('.benefit-addon').html()).toBe('%');
                    view.$el.find('[name=benefit_type]').val('Absolute').trigger('change');
                    expect(view.$el.find('.benefit-addon').html()).toBe('$');
                });

                it('should toggle upper limit on the benefit value input', function () {
                    view.$el.find('[name=code_type]').val('enrollment').trigger('change');
                    expect(view.$el.find('[name="benefit_value"]').attr('max')).toBe('100');
                    view.$el.find('[name=benefit_type]').val('Absolute').trigger('change');
                    expect(view.$el.find('[name="benefit_value"]').attr('max')).toBe('');
                });

                it('should show the code field only for multi-use vouchers', function () {
                    view.$el.find('[name=voucher_type]').val('Single use').trigger('change');
                    expect(visible('[name=code]')).toBe(false);
                    view.$el.find('[name=voucher_type]').val('Once per customer').trigger('change');
                    expect(visible('[name=code]')).toBe(true);
                });

                it('should show the usage number field only for multi-use vouchers', function () {
                    view.$el.find('[name=voucher_type]').val('Single use').trigger('change');
                    expect(visible('[name=max_uses]')).toBe(false);
                    view.$el.find('[name=voucher_type]').val('Once per customer').trigger('change');
                    expect(visible('[name=max_uses]')).toBe(true);
                });
            });

            describe('dynamic catalog', function () {
                beforeEach(function () {
                    view.$el.find('[name=catalog_type]').val('Multiple courses').trigger('change');
                });

                it('should call previewCatalog when Preview Catalog button was clicked', function () {
                    spyOn(view, 'previewCatalog');
                    view.delegateEvents();

                    view.$el.find('[name=preview_catalog]').trigger('click');
                    expect(view.previewCatalog).toHaveBeenCalled();
                });

                it('should call getHelpWithCatalog when Get Help button was clicked', function () {
                    spyOn(view, 'getHelpWithCatalog');
                    view.delegateEvents();

                    view.$el.find('[name=catalog_help]').trigger('click');
                    expect(view.getHelpWithCatalog).toHaveBeenCalled();
                });

                it('should call toggleFields when Catalog Type is changed', function () {
                    var catalogQueryFormGroup = view.$el.find('[name=catalog_query]').closest('.form-group'),
                        courseSeatTypesFormGroup = view.$el.find('[name=course_seat_types]').closest('.form-group'),
                        courseIDFormGroup = view.$el.find('[name=course_id]').closest('.form-group'),
                        seatTypeFormGroup = view.$el.find('[name=seat_type]').closest('.form-group');

                    view.model.set('catalog_type', 'Single course');
                    view.toggleFields();

                    expect(catalogQueryFormGroup.hasClass('hidden')).toBeTruthy();
                    expect(courseSeatTypesFormGroup.hasClass('hidden')).toBeTruthy();
                    expect(courseIDFormGroup.hasClass('hidden')).toBeFalsy();
                    expect(seatTypeFormGroup.hasClass('hidden')).toBeFalsy();

                    view.model.set('catalog_type', 'Multiple courses');
                    view.toggleFields();

                    expect(catalogQueryFormGroup.hasClass('hidden')).toBeFalsy();
                    expect(courseSeatTypesFormGroup.hasClass('hidden')).toBeFalsy();
                    expect(courseIDFormGroup.hasClass('hidden')).toBeTruthy();
                    expect(seatTypeFormGroup.hasClass('hidden')).toBeTruthy();
                });

                it('should list the courses when the previewCatalog is called', function () {
                    var event = $.Event('click');

                    spyOn(event, 'preventDefault');
                    view.previewCatalog(event);

                    expect(event.preventDefault).toHaveBeenCalled();
                    expect(view.$el.find('#number_of_courses > .value').html()).toEqual('2');
                    expect(view.$el.find('#courses > .value > ul').children().length).toEqual(2);
                });

                it('should provide help when the getHelpWithCatalog is called', function () {
                    var event = $.Event('click');

                    spyOn(event, 'preventDefault');
                    view.getHelpWithCatalog(event);

                    expect(event.preventDefault).toHaveBeenCalled();
                });
            });
        });
    }
);
